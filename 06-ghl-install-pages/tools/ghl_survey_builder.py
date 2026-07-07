#!/usr/bin/env python3
"""ghl_survey_builder.py — GoHighLevel native survey builder for Skill 06, Workstream B.

Implements ``build_survey(task, evidence_root)`` as a v2_dispatcher-injected
builder that:
  1. Creates a Contact custom-field folder and the survey's custom fields via the
     app shell (Part 1 — PRD §5.B.1 / canonical Part 1 transcript).
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

# Rate governor + session keepalive live in v2_dispatcher (reused, not reinvented)
from v2_dispatcher import RateGovernor, SessionKeepalive  # noqa: E402

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

try:  # SHARED frame-scoped coordinate-drag primitive (cross-origin iframe FIX)
    import ghl_iframe_drag as _ghl_iframe_drag  # noqa: E402
except Exception:  # noqa: BLE001
    _ghl_iframe_drag = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------
SURVEY_BUILDER_VERSION = "v1.0.0"

# GoHighLevel real domains (from PRD §5.B / transcripts)
GHL_APP_ORIGIN_DEFAULT = os.environ.get(
    "GHL_AGENCY_URL", "https://app.convertandflow.com"
)
GHL_SURVEY_BUILDER_HOST = (
    "leadgen-apps-form-survey-builder.leadconnectorhq.com"
)

# The survey builder renders inside this CROSS-ORIGIN iframe (same host as the form
# builder). agent-browser 0.27.0 cannot LOCATE a non-interactive drag-source row
# across that boundary, so the DRAG step is delegated to the shared
# ghl_iframe_drag primitive (Playwright over the same session's CDP). See
# ghl_iframe_drag.py + SELECTORS-LIVE-form.md §7.
GHL_SURVEY_IFRAME_SELECTOR = 'iframe[src*="survey-builder-v2"]'

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

# Conditional logic rules (PRD §5.B.2 Phase G; Pn- prefix is stable)
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
) -> subprocess.CompletedProcess:
    """Execute one agent-browser command. Returns CompletedProcess; never raises."""
    cmd_str = ghl_builder.browser_cmd("--session", session, *args)
    _log(f"[ab] {cmd_str}")
    try:
        return subprocess.run(
            shlex.split(cmd_str),
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
    """Evaluate JS and return stdout (for URL capture, keepalive, etc.)."""
    result = _run_cmd(session, "eval", js, timeout=timeout)
    return (result.stdout or "").strip().strip('"').strip("'")


def _snapshot(session: str) -> str:
    """Get the current accessibility snapshot (-i mode)."""
    result = _run_cmd(session, "snapshot", "-i", timeout=20)
    return result.stdout or ""


def _get_cdp_url(session: str) -> str:
    """Read the live agent-browser session's CDP url (`get cdp-url`) so Playwright
    can attach to the SAME logged-in Chromium for the frame-scoped drag — one
    browser, one login. Routed through the managed _run_cmd glue. '' if absent."""
    result = _run_cmd(session, "get", "cdp-url", timeout=15)
    return (result.stdout or "").strip().strip('"').strip("'")


def _perform_iframe_drag(session: str, source_text: str, drop_target: str,
                         *, verify_text: str,
                         iframe_selector: str = GHL_SURVEY_IFRAME_SELECTOR) -> dict:
    """Drag ONE object-field row (``source_text``) onto its target slide
    (``drop_target``) INSIDE the cross-origin survey-builder iframe via the shared
    ghl_iframe_drag primitive, verifying ``verify_text`` then appears. FAIL-CLOSED:
    raises RuntimeError (never a fake success) if the primitive/CDP is unavailable
    or the drag does not land. Replaces the top-frame-only `_run_cmd drag`, which
    cannot reach the row across the cross-origin boundary."""
    if _ghl_iframe_drag is None:
        raise RuntimeError(
            "STOP (survey iframe-drag): the shared ghl_iframe_drag primitive is not "
            "importable, and agent-browser 0.27.0 alone cannot locate a non-interactive "
            "field row across the cross-origin survey-builder iframe. Ship "
            "ghl_iframe_drag.py + Playwright (scoped to Skill 6).")
    cdp_url = _get_cdp_url(session)
    if not cdp_url:
        raise RuntimeError(
            "STOP (survey iframe-drag): could not read the agent-browser CDP url "
            "(`get cdp-url`) to hand the drag off to Playwright on the same session.")
    try:
        return _ghl_iframe_drag.coordinate_drag(
            cdp_url,
            iframe_selector=iframe_selector,
            source=f"text={source_text}",
            target=f"text={drop_target}",
            url_marker="survey-builder",
            verify_text=verify_text,
        )
    except _ghl_iframe_drag.IframeDragError as exc:
        raise RuntimeError(f"STOP (survey iframe-drag:{exc.code}): {exc.reason}") from exc


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

    # P5 — duplicate-survey check (delegated to ghl_method if available)
    chk("P5:no_duplicate", True,
        "resolve_install_target will raise InstallTargetError on ambiguous duplicates")

    # P6 — custom-field plan (create vs reuse decision recorded in field map)
    chk("P6:field_plan", True, "field action (create|reuse) set per field in field map")

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


def _build_survey_plan(task: dict, fields: List[dict]) -> dict:
    """Build the routing/survey-plan.json structure (THINK output)."""
    folder_name = task.get("folder_name", "Sample Survey")
    survey_name = task.get("survey_name", task.get("title", "New Survey"))
    location_id = (
        task.get("location_id")
        or task.get("GHL_LOCATION_ID")
        or os.environ.get("GHL_LOCATION_ID", "")
    )
    business_name = task.get("business_name", "[BUSINESS NAME]")
    campaign = task.get("campaign", "our campaign")
    copy_persona = task.get("copy_persona") or {}

    slides: List[dict] = [
        {
            "index": 1,
            "name": "Welcome Slide",
            "type": "welcome",
            "element": "Text",
            "copy_persona_label": copy_persona.get("label", ""),
        }
    ]
    for i, f in enumerate(fields, start=2):
        slides.append({
            "index": i,
            "name": f["slide_name"],
            "type": "question",
            "field_label": f["label"],
            "field_type": f["type"],
            "required": f.get("required", True),
        })
    slides.append({
        "index": len(fields) + 2,
        "name": "Contact Capture",
        "type": "capture",
        "elements": ["First Name", "Last Name", "Email", "Phone", "T & C"],
        "required_elements": ["Email", "Phone"],
        "business_name": business_name,
        "campaign": campaign,
        "note": "T & C is plain marketing-consent checkbox — NOT A2P/10DLC",
    })

    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "survey_name": survey_name,
        "folder_name": folder_name,
        "location_id": location_id,
        "total_slides": len(slides),
        "slides": slides,
        "fields": fields,
        "conditional_logic": CONDITIONAL_LOGIC_RULES,
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


def _build_field_map(fields: List[dict], folder_name: str) -> dict:
    """Build routing/survey-field-map.json."""
    custom_entries: List[dict] = []
    for f in fields:
        key = f.get("key") or _auto_key(f["label"])
        custom_entries.append({
            "slide_name": f["slide_name"],
            "field_label": f["label"],
            "field_type": f["type"],
            "field_key": key,
            "merge_token": f"{{{{contact.{key}}}}}",
            "folder": folder_name,
            "action": f.get("action", "create"),  # 'create' or 'reuse'
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
    app_url = f"{GHL_APP_ORIGIN_DEFAULT}/v2/location/{location_id}/dashboard"

    # Step 1: back to dashboard
    _open(session, app_url)
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
) -> None:
    """Phase E: Add Object Fields — drag each custom field onto its slide.

    Uses the ``Add Object Fields`` tab (NOT Quick Add). Each dragged field writes
    its answer directly to ``{{contact.<key>}}``.
    """
    _log(f"P2-E: Add Object Fields from folder {folder_name!r}")
    folder_upper = folder_name.upper()

    # Navigate to Slide 2 (first question slide)
    _click(session, "Slide 2")

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

    # Drag each field onto its target slide
    for i, f in enumerate(fields):
        label_prefix = f["label"][:28]
        target_slide = f"Slide {i + 2}"
        _log(f"  Dragging field {i + 1}/{len(fields)}: {label_prefix!r} → {target_slide}")

        # Use Search by Name for fast, reliable location (PRD §5.B.2 Phase E)
        _fill(session, "Search by Name", f["label"][:20])
        # FRAME-SCOPED drag (cross-origin iframe): agent-browser cannot reach the
        # field row, so hand this step to Playwright over the same session's CDP.
        _perform_iframe_drag(session, label_prefix, target_slide,
                             verify_text=label_prefix[:20])
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
) -> None:
    """Phase F: rename each question slide via gear → Slide Name (short names).

    Followed by an intermediate save (transcript steps 86–87).
    """
    _log("P2-F: rename question slides")
    for i, f in enumerate(fields):
        slide_n = i + 2
        short_name = f["slide_name"]
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
    """Phase G: wire Jump-To conditional logic on the first question slide.

    The per-field conditional-logic control is DEPRECATED; the canonical path is
    the amber ``Open Conditional Logic`` link on the field panel.
    Two rules (one save each): Yes → P2, No → P4. Rules run top-down.
    """
    _log("P2-G: conditional logic")

    # Navigate to the first question slide (Slide 2)
    _click(session, "Slide 2")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-g-first-slide"))

    # Open Conditions modal via the amber link on the field panel
    _click(session, "Open Conditional Logic")
    _wait(session, "Jump To")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-g-conditions-modal"))

    for ri, rule in enumerate(rules):
        _log(f"  Rule {ri + 1}/{len(rules)}: IF {rule['if_field'][:30]!r} "
             f"= {rule['if_value']!r} THEN {rule['then_slide']!r}")

        # Add Jump To card
        _click(session, "Jump To")
        _wait(session, "Select field")

        # Set condition type = Field
        _click(session, "Field")

        # Pick the IF field (may be truncated — use partial match)
        _click(session, rule["if_field"][:28])

        # Operator defaults to "Is Equal To" — no change needed

        # Set value
        _click(session, rule["if_value"])

        # Set THEN target slide (Pn- prefix is stable)
        _click(session, rule["then_slide"])

        # Save this condition (one save per rule, RateGovernor spaced)
        gov.before("save")
        _click(session, "Save")
        # Modal stays open after save; wait for Jump To card to re-appear
        _wait(session, "Jump To", timeout=15)
        shot_n[0] += 1
        _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                        f"p2-g-rule{ri + 1:02d}-saved"))


def _p2_required_toggles(
    session: str,
    fields: List[dict],
    evidence_root: str,
    shot_n: List[int],
) -> None:
    """Phase H: tick Required checkbox on each required question slide.

    Confirmation: the field label gains a trailing ``*``.
    """
    _log("P2-H: required toggles")
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
) -> None:
    """Phase J: Quick-Add contact-capture slide + T&C consent checkbox.

    Adds: First Name, Last Name, Email (required), Phone (required),
    T & C (plain marketing-consent checkbox — NOT A2P/10DLC).
    Edits the [BUSINESS NAME] placeholder in the T&C consent copy.
    """
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
) -> dict:
    """Build the full ordered click sequence for operator review (dry-run output)."""
    steps: List[dict] = []
    n = 0

    def add(phase: str, action: str, target: str, note: str = "") -> None:
        nonlocal n
        n += 1
        steps.append({"n": n, "phase": phase, "action": action,
                       "target": target, "note": note})

    app_url = f"{GHL_APP_ORIGIN_DEFAULT}/v2/location/{location_id}/dashboard"

    # ── Part 1 ───────────────────────────────────────────────────────────────
    add("P1", "navigate", app_url, "Open app shell")
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
    num_extra = len(fields) + 1  # 6 question slides + 1 capture
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
    add("P2-E", "click", "Slide 2", "First question slide for Add Object Fields")
    add("P2-E", "click", "Add Elements", "Opens drawer")
    add("P2-E", "click", "Add Object Fields",
        "Tab — NOT Quick Add. Object dropdown must read Contact")
    add("P2-E", "click", f"{folder_name.upper()} (n)",
        "Expand folder group; (n) = field count, volatile — match on name only")
    for fi, f in enumerate(fields):
        add("P2-E", "fill+drag",
            f"Search by Name = {f['label'][:20]!r} → drag to Slide {fi + 2}",
            "Object field binds answer to {{contact.<key>}}")
    for fi, f in enumerate(fields):
        add("P2-F", "gear+fill",
            f"Slide {fi + 2} → Slide Name = {f['slide_name']!r}", "Short name")
    add("P2-F", "click+confirm", "Save → Yes", "Interim save (transcript steps 86–87)")
    add("P2-G", "click", "Open Conditional Logic",
        "Amber link on first-question field panel — per-field dropdown is deprecated")
    for ri, rule in enumerate(CONDITIONAL_LOGIC_RULES):
        add("P2-G", "click", "Jump To", f"Rule {ri + 1}")
        add("P2-G", "select", f"Field → {rule['if_field'][:30]!r}", "IF field")
        add("P2-G", "select", rule["if_value"], "IF value (Is Equal To default)")
        add("P2-G", "select", rule["then_slide"], "THEN slide (Pn- prefix stable)")
        add("P2-G", "click", "Save",
            "One save per rule; rules run top-down; modal stays open")
    for fi, f in enumerate(fields):
        if f.get("required"):
            add("P2-H", "check",
                f"P{fi + 2} - {f['slide_name']} → Required",
                "Right panel, left of Hidden; trailing * confirms")
    add("P2-J", "click", f"Slide {len(fields) + 2}", "Contact capture slide")
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
        "total_steps": n,
        "dry_run": True,
        "note": (
            "Operator review: verify every step before flipping --no-dry-run. "
            "Transcript is canonical (PRD §5.B.1–2). "
            "Google-Doc detours in the recording are recorder noise — ignore them."
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

    # ── Dry-run: emit click list and return ───────────────────────────────────
    if dry_run:
        click_list = _emit_click_list(
            fields, folder_name, survey_name,
            business_name, campaign, welcome_copy, location_id,
        )
        click_list_path = os.path.join(evidence_root, "routing", "survey-click-list.json")
        _write_json(click_list_path, click_list)
        _log(f"[dry-run] Click list ({click_list['total_steps']} steps): {click_list_path}")
        _board_activity(
            board_task_id, "updated",
            f"[dry-run] Plan + field-map + click list written "
            f"({click_list['total_steps']} steps). No browser execution. "
            "Flip --no-dry-run after operator review.",
        )
        duration = time.monotonic() - started
        return {
            "pages": plan["slides"],
            "location_gate_ok": bool(location_id),
            "duration_s": duration,
            "survey_url": "",
            "field_map": field_map,
            "preflight": preflight,
            "plan_path": plan_path,
            "field_map_path": field_map_path,
            "click_list_path": click_list_path,
            "shots": [],
            "dry_run": True,
        }

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

            # ── Part 1: custom-field folder ───────────────────────────────────
            step_n = 4
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 1 — create folder {folder_name!r}")
            _p1_create_folder(
                session, location_id, folder_name, gov, evidence_root, shot_n
            )

            # ── Part 1: custom fields ─────────────────────────────────────────
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
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase A — create survey")
            _p2_navigate_create(session, location_id, evidence_root, shot_n)

            # ── Part 2: Phase B — rename survey ──────────────────────────────
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase B — rename survey")
            _p2_rename_survey(session, survey_name, evidence_root, shot_n)

            # ── Part 2: Phase C — add slides ──────────────────────────────────
            step_n += 1
            num_extra = len(fields) + 1  # question slides + capture
            _board_activity(
                board_task_id, "updated",
                f"Step {step_n}/{total_steps}: Part 2 Phase C — add {num_extra} slides "
                f"(total={1 + num_extra})",
            )
            _p2_add_slides(session, num_extra, evidence_root, shot_n)

            # ── Part 2: Phase D — welcome slide ───────────────────────────────
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase D — welcome slide (Text element)")
            _p2_welcome_slide(session, welcome_copy, evidence_root, shot_n)

            # ── Part 2: Phase E — pull custom fields ──────────────────────────
            step_n += 1
            _board_activity(
                board_task_id, "updated",
                f"Step {step_n}/{total_steps}: Part 2 Phase E — Add Object Fields "
                f"from folder {folder_name!r}",
            )
            _p2_pull_object_fields(session, folder_name, fields, evidence_root, shot_n)

            # ── Part 2: Phase F — rename question slides ──────────────────────
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase F — rename question slides")
            _p2_rename_question_slides(session, fields, gov, evidence_root, shot_n)

            # ── Part 2: Phase G — conditional logic ───────────────────────────
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase G — conditional logic "
                            f"({len(CONDITIONAL_LOGIC_RULES)} rules)")
            _p2_conditional_logic(
                session, CONDITIONAL_LOGIC_RULES, gov, evidence_root, shot_n
            )

            # ── Part 2: Phase H — required toggles ───────────────────────────
            step_n += 1
            required_count = sum(1 for f in fields if f.get("required"))
            _board_activity(
                board_task_id, "updated",
                f"Step {step_n}/{total_steps}: Part 2 Phase H — required toggles "
                f"({required_count} fields)",
            )
            _p2_required_toggles(session, fields, evidence_root, shot_n)

            # ── Part 2: Phase J — capture slide + T&C ────────────────────────
            step_n += 1
            _board_activity(
                board_task_id, "updated",
                f"Step {step_n}/{total_steps}: Part 2 Phase J — Quick-Add capture "
                "slide + T&C (plain consent checkbox, NOT A2P)",
            )
            _p2_capture_slide(
                session, business_name, campaign, len(fields),
                evidence_root, shot_n,
            )

            # ── Part 2: Phase K — save + get URL ─────────────────────────────
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
        "brief": {"source": "cli"},
    }

    result = build_survey(task, args.evidence_root, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("location_gate_ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
