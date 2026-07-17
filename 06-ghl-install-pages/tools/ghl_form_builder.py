#!/usr/bin/env python3
"""ghl_form_builder.py — GoHighLevel (Convert and Flow) native FORM builder for Skill 06.

STATUS: LIVE (v0.1.0). Field placement is FULLY IMPLEMENTED — F5 Quick-Add
(standard) and F6 Add-Object-Fields (pre-created ``zhc_`` custom) fields are placed
by runtime snapshot-and-bind: snapshot the live (auto-inlined) builder iframe, locate
the tile/field by its VISIBLE TEXT, drag it onto the canvas, then bind its property
panel (Label / Query Key / Field Width / Required|Hidden) by visible label — never an
invented CSS selector, and a genuine unplaceable field is a STOP-and-report (NOT the
default path). Dry-run + selftest stay dependency-free (no network / no browser); the
selftest drives the full placement path against a mocked browser. The live path drives
the real GHL builder end-to-end (seed → create → place → embed → verify → delete).

WHY THIS EXISTS
---------------
Skill 6 is the ONE GHL delivery rail. It already builds funnels, websites, and
surveys (``ghl_survey_builder.py``). This tool ADDS the FORMS capability:
create a form, add standard + custom fields, retrieve the embed/JS snippet,
embed it into a GHL page/funnel/website (with CSS polish), and attach tags.

TWO-LAYER SPLIT (the whole point)
---------------------------------
The agent BROWSER OPERATOR is NOT smart — it often runs on MiniMax-M3 (see
``EXECUTE_LADDER``), far weaker than the reasoning model. So this module is a
hard split:

  • SMART / THINK layer  (this Python, run under a reasoning model): decides
    WHAT form to build and WHY — which standard fields, which CUSTOM fields and
    tags are needed, their exact labels / keys / widths / required-hidden flags,
    and the exact embed target. It PRE-CREATES every custom field and tag through
    the GHL API layer (Skill 44 — see below) so nothing ambiguous is left to the
    browser. It emits a fully-explicit, ordered CLICK LIST.

  • DUMB / DO layer  (agent-browser, MiniMax-M3): executes the click list
    verbatim. Every target string, label, width, and toggle is spelled out. The
    browser makes NO decisions. Locate by a11y ref first (``snapshot -i`` →
    ``@eN``), visible-text fallback, documented CSS only as last resort, explicit
    waits on visible text (never fixed sleeps), a screenshot after every step.

GLUE, NOT THE CLICKER — like ``ghl_survey_builder.py``, this Python emits ordered
browser-control commands via ``ghl_builder.browser_cmd`` → ``agent-browser``; it
NEVER mutates GHL state directly and owns only its own ledgers.

CUSTOM FIELDS + TAGS GO THROUGH THE API LAYER (Skill 44), NOT THE BROWSER
------------------------------------------------------------------------
The video shows two ways to get a custom field onto a form:
  (A) create-on-the-fly by dragging e.g. a Rating element — GHL invents a random
      unique-key suffix ("rating rat584…") that a human then renames; and
  (B) Add Object Fields — drag a PRE-CREATED custom field; its unique key +
      custom-field name are LOCKED, only the Label is editable.
Path (A) leaves naming/keys to the dumb browser (judgment + a random key = fragile
+ un-prefixed). This design REJECTS (A) for agent builds and standardizes on (B):

  → The THINK layer emits a DEPENDENCY PLAN (custom fields + tags, each with a
    ``zhc_`` key and a create|reuse action). The GHL-API operator **Skill 44
    (``44-convert-and-flow-operator`` — the ``caf`` CLI, PIT-authenticated)**
    creates/looks-up those fields + tags on the location (it already "REFUSES to
    build a workflow whose dependencies (tags, custom fields) are missing"). Only
    then does the browser DRAG the pre-created ``zhc_`` fields in via Add Object
    Fields. This matches Skill 6's "grocery-shopping rule: pre-build
    forms/calendars/tags/workflows (Skill 44) BEFORE the page."

ZHC AGENT-CREATED MARKER — PINNED CONVENTION (enforced here)
------------------------------------------------------------
Every agent-created CUSTOM FIELD and TAG carries a lowercase ``zhc`` marker so it
is auditable and de-duplicated:
  • Custom field UNIQUE KEY (GHL "custom field name" — lowercase, no spaces):
        ``zhc_<snake_slug>``      e.g. ``zhc_podcast_rating``
    → merge token ``{{contact.zhc_podcast_rating}}``. The client-facing LABEL
      stays human ("Podcast Rating"); the MARKER lives in the KEY.
  • Tag (GHL lowercases tags anyway):
        ``zhc_<snake_slug>``      e.g. ``zhc_podcast_lead``
  • Idempotency: BEFORE creating, the API layer GETs existing custom fields / tags
    and REUSES any whose key/name already equals the target ``zhc_…`` value —
    never create a duplicate. ``plan_dependencies()`` stamps action=reuse|create.
  • The FORM's own NAME (the container shown in the GHL Forms list) follows the
    existing fleet convention — UPPERCASE ``ZHC `` prefix (``ensure_zhc_name`` /
    ``ghl_builder.ensure_zhc_prefix``), e.g. "ZHC Podcast Signup Form". Two
    conventions, on purpose: container NAMES → ``ZHC `` (fleet), machine
    KEYS/TAGS → ``zhc_`` (must be lowercase / no-space per GHL).

MODEL DOCTRINE — client-owned providers, NEVER Anthropic
--------------------------------------------------------
Ollama Cloud → OpenRouter equivalent → Gemini last-resort, thinking=high on every
rung. MiniMax M2 is BANNED. Browser-control (execution) uses MiniMax M3 only →
DeepSeek v4 pro. Vision QC uses MiniMax M3 only. No Anthropic slug ever.

NO LOGIN CODE — auth is handled upstream by the dispatcher / seeded browser
session (token-only doctrine). The CI guard forbids login patterns outside
``ghl_auth_fallback.py`` / ``ghl_login_browser.py``.

USAGE
-----
    result = build_form(task, "/tmp/form-run-01")            # dry_run=True default
    result = build_form(task, "/tmp/form-run-01", dry_run=False)   # live (gated)
    python3 ghl_form_builder.py --dry-run --location-id LOC123 --form-name "Podcast Signup"
    python3 ghl_form_builder.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Soft imports — selftest + dry-run stay runnable with ZERO deps (no ghl_builder /
# browser_manager needed). The LIVE browser path requires the real skill modules
# (this file ships IN 06-ghl-install-pages/tools/) and asserts their presence first.
# ---------------------------------------------------------------------------
try:  # skill glue: browser_cmd + headless_guard + ZHC name helper
    import ghl_builder  # type: ignore
except Exception:  # noqa: BLE001
    ghl_builder = None  # type: ignore

try:  # singleton pooled browser session
    import browser_manager  # type: ignore
except Exception:  # noqa: BLE001
    browser_manager = None  # type: ignore

try:  # SHARED frame-scoped coordinate-drag primitive (Playwright over agent-browser CDP)
    import ghl_iframe_drag  # type: ignore
except Exception:  # noqa: BLE001
    ghl_iframe_drag = None  # type: ignore

try:  # rate limiter + keepalive + F5(b) pre-phase re-mint (reused from dispatcher when present)
    from v2_dispatcher import RateGovernor as _RealRateGovernor  # type: ignore
    from v2_dispatcher import SessionKeepalive as _RealKeepalive  # type: ignore
    from v2_dispatcher import remint_if_stale as _real_remint_if_stale  # type: ignore
except Exception:  # noqa: BLE001
    _RealRateGovernor = None  # type: ignore
    _RealKeepalive = None  # type: ignore
    _real_remint_if_stale = None  # type: ignore

# U8/U10 — shared phase-checkpoint store + the uniform RUN REPORT emitter. A HARD
# import (not a soft one): resume and the run report are part of the CLI contract,
# and silently degrading to "no checkpoints" would be exactly the kind of gate that
# fails open. It ships in the same tools/ dir as this file — bootstrap the path so
# an import from any cwd resolves it.
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_run_state  # noqa: E402
from ghl_run_state import PhaseSpec  # noqa: E402


# ── U8: the form builder's declared phase walk (the click list's own F1…F13) ────
# ``resumable=False`` = ALWAYS re-executes on resume:
#   * F1 — NAVIGATION to the Forms list. You cannot skip walking back in.
#   * F13 — the render VERIFY. A gate a resume skips is not a gate; it re-runs.
# F2 (create the form) IS resumable, and skipping it is the whole point: on resume
# the walk routes STRAIGHT to the already-created form's builder URL instead of
# creating a second, duplicate form.
FORM_PHASES: List[PhaseSpec] = [
    PhaseSpec("F1",  "navigate to Forms list",         resumable=False),
    PhaseSpec("F2",  "create the form"),
    PhaseSpec("F3",  "rename the form"),
    PhaseSpec("F4",  "delete unwanted default fields"),
    PhaseSpec("F5",  "place standard fields"),
    PhaseSpec("F6",  "place pre-created custom fields"),
    PhaseSpec("F7",  "field settings"),
    PhaseSpec("F8",  "styling / options"),
    PhaseSpec("F9",  "save"),
    PhaseSpec("F10", "capture embed + share link"),
    PhaseSpec("F11", "embed → page splice handoff"),
    PhaseSpec("F12", "tag attachment handoff"),
    PhaseSpec("F13", "render verify",                  resumable=False),
]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------
FORM_BUILDER_VERSION = "v0.1.1"   # v0.1.1 (P3-04 c4): iframe-drag/remove/rename failure
                                   # reasons now carry the CC board-note taxonomy prefix
                                   # (SELECTOR-MISS/VERIFY-FAIL) + frame-origin context

GHL_APP_ORIGIN_DEFAULT = os.environ.get("GHL_AGENCY_URL", "https://app.convertandflow.com")
# The form builder loads inside the same leadgen iframe host as the survey builder.
# RUNTIME SNAPSHOT-GATED — confirm the exact path on the first live run.
GHL_FORM_BUILDER_HOST = "leadgen-apps-form-survey-builder.leadconnectorhq.com"

ZHC_NAME_PREFIX = "ZHC "   # container NAMES (form/funnel/website) — fleet convention
ZHC_KEY_PREFIX = "zhc_"    # machine KEYS (custom-field keys + tags) — lowercase

# Quick-Add taxonomy from the transcript (02:27–03:50). The THINK layer uses this
# to route a requested STANDARD field to the right category → element tile.
QUICK_ADD_TAXONOMY: Dict[str, List[str]] = {
    "Personal Info": ["Full Name", "First Name", "Last Name", "Date of Birth", "Phone", "Email"],
    "Submit": ["Submit"],
    "Payments": ["Sell Products", "Collect Payment"],
    "Address": ["Address", "City", "State", "Country", "Postal Code", "Organization", "Website"],
    "Text": ["Single Line", "Multi Line", "Text Box", "Text Box List"],
    "Choice": ["Single Dropdown", "Multi Dropdown", "Checkboxes", "Radio"],
    "Rating": ["Rating"],
    "Customized": ["Text", "HTML", "Captcha", "Source", "Terms & Conditions", "Score"],
    "Other": ["Image", "File Upload", "Monetary", "Number", "Date Picker",
              "Picture Date Picker", "Signature"],
}

# Fields GHL puts on a scratch form by default (01:39–02:27).
DEFAULT_FORM_FIELDS = ["First Name", "Last Name", "Phone", "Email", "Terms & Conditions"]

# ── Model ladders (Ollama-Cloud first → OpenRouter → Gemini last resort) ──────
# thinking=high on every rung. MiniMax M2 BANNED. No Anthropic slug. Browser
# execution = MiniMax M3 → DeepSeek v4 pro. Vision QC = MiniMax M3 only.
THINK_LADDER: List[dict] = [
    {"rung": 1, "provider": "ollama-cloud", "model": "glm-5.2:cloud", "role": "reasoning", "thinking": "high"},
    {"rung": 2, "provider": "ollama-cloud", "model": "kimi-k2.6:cloud", "role": "reasoning", "thinking": "high"},
    {"rung": 3, "provider": "ollama-cloud", "model": "deepseek-v4-pro:cloud", "role": "reasoning", "thinking": "high"},
    {"rung": 4, "provider": "openrouter", "model": "z-ai/glm-5.2", "role": "reasoning", "thinking": "high"},
    {"rung": 5, "provider": "openrouter", "model": "deepseek/deepseek-v4-pro", "role": "reasoning", "thinking": "high"},
    {"rung": 6, "provider": "openrouter", "model": "google/gemini-3.5-flash-lite",
     "role": "last-resort", "thinking": "high", "gate": "only_if_live_and_credited"},
]
EXECUTE_LADDER: List[dict] = [
    {"rung": 1, "provider": "ollama-cloud", "model": "minimax-m3:cloud",
     "role": "browser-control", "thinking": "high", "probe_gated": True},
    {"rung": 2, "provider": "openrouter", "model": "minimax/minimax-m3",
     "role": "browser-control", "thinking": "high", "probe_gated": True},
    {"rung": 3, "provider": "ollama-cloud", "model": "deepseek-v4-pro:cloud",
     "role": "browser-control", "thinking": "high"},
    {"rung": 4, "provider": "openrouter", "model": "deepseek/deepseek-v4-pro",
     "role": "browser-control", "thinking": "high"},
    {"rung": 5, "provider": "openrouter", "model": "google/gemini-3.5-flash-lite",
     "role": "last-resort", "thinking": "high", "gate": "only_if_live_and_credited"},
]
QC_LADDER: List[dict] = [
    {"rung": 1, "provider": "ollama-cloud", "model": "minimax-m3:cloud",
     "role": "qc+vision", "thinking": "high", "probe_gated": True},
    {"rung": 2, "provider": "openrouter", "model": "minimax/minimax-m3",
     "role": "qc+vision", "thinking": "high", "probe_gated": True},
    {"rung": 3, "provider": "openrouter", "model": "google/gemini-3.5-flash-lite",
     "role": "last-resort", "thinking": "high", "gate": "only_if_live_and_credited"},
]

# Selector strategy the DUMB browser must apply on EVERY click-list step.
SELECTOR_STRATEGY = [
    "1. a11y ref first: `snapshot -i` → pick the @eN ref for the target's visible text/role.",
    "2. visible-text fallback: click the exact `target` string (labels below are verbatim).",
    "3. documented CSS only as a last resort; NEVER ship invented CSS as fact.",
    "4. wait on a visible-text condition before AND after each material step (no fixed sleeps).",
    "5. screenshot after every material step to shots/NNN-<phase>.png.",
    "6. one action per command; the browser decides NOTHING — every target is pre-specified.",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _log(msg: str) -> None:
    print(f"[ghl_form_builder] {msg}", file=sys.stderr, flush=True)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _slug(text: str) -> str:
    """Lowercase snake slug: no spaces / special chars (GHL key + tag rule)."""
    s = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())
    return s.strip("_")[:48]


# ---------------------------------------------------------------------------
# ZHC marker helpers (PINNED convention — see module docstring)
# ---------------------------------------------------------------------------
def zhc_field_key(name_or_slug: str) -> str:
    """Custom-field unique key: ``zhc_<snake_slug>`` (idempotent, never double-prefixed)."""
    slug = _slug(name_or_slug)
    if slug.startswith(ZHC_KEY_PREFIX):
        return slug
    return f"{ZHC_KEY_PREFIX}{slug}"


def zhc_tag(name_or_slug: str) -> str:
    """Tag value: ``zhc_<snake_slug>`` (GHL lowercases tags; idempotent)."""
    slug = _slug(name_or_slug)
    if slug.startswith(ZHC_KEY_PREFIX):
        return slug
    return f"{ZHC_KEY_PREFIX}{slug}"


def ensure_zhc_name(name: str) -> str:
    """Container NAME → UPPERCASE ``ZHC `` prefix (case-insensitive, no double-prefix).

    Prefers the live skill's ``ghl_builder.ensure_zhc_prefix`` when importable so
    the forms rail stays byte-identical to the funnels/websites/surveys rail.
    """
    if ghl_builder is not None and hasattr(ghl_builder, "ensure_zhc_prefix"):
        try:
            return ghl_builder.ensure_zhc_prefix(name)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    if name.strip().lower().startswith("zhc "):
        return name.strip()
    return f"{ZHC_NAME_PREFIX}{name.strip()}"


def is_zhc_field_key(key: str) -> bool:
    return key.lower().startswith(ZHC_KEY_PREFIX)


def is_zhc_tag(tag: str) -> bool:
    return tag.lower().startswith(ZHC_KEY_PREFIX)


# ---------------------------------------------------------------------------
# THINK layer — field resolution, dependency plan, form plan, click list
# ---------------------------------------------------------------------------
def _find_quick_add_category(element: str) -> Optional[str]:
    for cat, tiles in QUICK_ADD_TAXONOMY.items():
        if element in tiles:
            return cat
    return None


def _resolve_fields(task: dict) -> List[dict]:
    """Normalize task['form_fields'] into fully-specified field dicts.

    Each field dict (input) may contain:
      source: "standard" | "custom"   (default inferred: standard if the element
                                        is a Quick-Add tile, else custom)
      element / label / field_type / width_pct / required / hidden / placeholder /
      query_key / options / settings
    """
    raw = task.get("form_fields")
    if not raw:
        raw = _reference_fields()
    resolved: List[dict] = []
    for f in raw:
        f = dict(f)
        label = f.get("label") or f.get("element") or "Field"
        element = f.get("element") or label
        source = f.get("source")
        if not source:
            source = "standard" if _find_quick_add_category(element) else "custom"
        entry = {
            "source": source,
            "element": element,
            "label": label,
            "field_type": f.get("field_type", "single_line"),
            "quick_add_category": _find_quick_add_category(element) if source == "standard" else None,
            "width_pct": int(f.get("width_pct", 100)),
            "required": bool(f.get("required", False)),
            "hidden": bool(f.get("hidden", False)),
            "placeholder": f.get("placeholder", ""),
            "options": [o.strip() for o in f.get("options", []) if str(o).strip()],
            "settings": f.get("settings", {}),
        }
        # required + hidden are mutually exclusive (transcript 14:09–14:12)
        if entry["required"] and entry["hidden"]:
            entry["hidden"] = False
            entry["_warning"] = "required+hidden both set → forced hidden=False (not both)"
        if source == "standard":
            # query key (URL param) — lowercase, no spaces/special (05:56–06:48)
            entry["query_key"] = f.get("query_key") or _slug(label)
        else:
            # CUSTOM field → carries the zhc_ marker on its key
            entry["field_key"] = zhc_field_key(f.get("field_key") or label)
            entry["merge_token"] = f"{{{{contact.{entry['field_key']}}}}}"
            entry["add_via"] = "add_object_fields"  # never create-on-the-fly
        resolved.append(entry)
    return resolved


def _reference_fields() -> List[dict]:
    """Reference form used by selftest + example dry-run (generic, no client names).

    Mirrors the video: standard City/State at 50% required, a custom Rating field,
    and a pre-created custom Facebook URL field.
    """
    return [
        {"source": "standard", "element": "First Name", "label": "First Name", "required": True},
        {"source": "standard", "element": "Last Name", "label": "Last Name", "required": True},
        {"source": "standard", "element": "Email", "label": "Email", "required": True},
        {"source": "standard", "element": "City", "label": "City", "width_pct": 50, "required": True},
        {"source": "standard", "element": "State", "label": "State", "width_pct": 50, "required": True},
        {"source": "custom", "element": "Rating", "label": "Podcast Rating",
         "field_key": "podcast_rating", "field_type": "rating", "required": True,
         "settings": {"icon": "thumbs_up", "icon_alignment": "left", "count": 5,
                      "store_as": "absolute"}},
        {"source": "custom", "element": "Single Line", "label": "Personal Facebook URL",
         "field_key": "facebook_url", "field_type": "single_line", "hidden": False},
    ]


def plan_dependencies(fields: List[dict], task: dict,
                      existing_field_keys: Optional[List[str]] = None,
                      existing_tags: Optional[List[str]] = None) -> dict:
    """Build the Skill-44 (GHL-API) dependency plan: custom fields + tags to
    create BEFORE the browser build, each stamped action=create|reuse (idempotent).

    ``existing_field_keys`` / ``existing_tags`` are what Skill 44's
    ``caf locations custom-fields`` / tag listing returns; when omitted the plan
    marks everything ``create`` and records that a live idempotency GET is required.
    """
    existing_field_keys = [k.lower() for k in (existing_field_keys or [])]
    existing_tags = [t.lower() for t in (existing_tags or [])]

    field_specs: List[dict] = []
    for f in fields:
        if f["source"] != "custom":
            continue
        key = f["field_key"]  # already zhc_-prefixed
        action = "reuse" if key.lower() in existing_field_keys else "create"
        field_specs.append({
            "field_key": key,               # zhc_<slug>
            "custom_field_name": key,       # GHL "custom field name" == the key
            "label": f["label"],            # client-facing, human
            "data_type": f["field_type"],
            "options": f.get("options", []),
            "settings": f.get("settings", {}),
            "merge_token": f["merge_token"],
            "action": action,
        })

    tag_specs: List[dict] = []
    for raw_tag in task.get("tags", []):
        tag = zhc_tag(raw_tag)
        action = "reuse" if tag in existing_tags else "create"
        tag_specs.append({"tag": tag, "action": action})

    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "owner_skill": "44-convert-and-flow-operator",
        "cli": "caf (PIT-authenticated)",
        "idempotency": {
            "live_get_required": not (existing_field_keys or existing_tags),
            "rule": "GET existing custom fields + tags; REUSE any matching zhc_ "
                    "key/name; only CREATE the remainder. Never duplicate.",
        },
        "custom_fields": field_specs,
        "tags": tag_specs,
        "tag_attachment": _tag_attachment_plan(task, tag_specs),
        "note": "Skill 44 creates/looks-up these on the location BEFORE the browser "
                "build. The browser then only DRAGS the pre-created zhc_ fields in "
                "via Add Object Fields. Custom-field create-on-the-fly is DISALLOWED.",
    }


def _tag_attachment_plan(task: dict, tag_specs: List[dict]) -> dict:
    """How the (already-created) tags get ATTACHED on submit.

    GHL's form builder has NO native 'add tag' control. Canonical path = a
    'Form Submitted' → 'Add Contact Tag' Workflow built by Skill 44. Documented
    alternative = a HIDDEN Tags object-field on the form (transcript 13:43–14:12).
    """
    return {
        "method": task.get("tag_attachment", "workflow"),  # "workflow" | "hidden_field"
        "workflow": {
            "owner_skill": "44-convert-and-flow-operator",
            "trigger": "Form Submitted",
            "filter": {"form": "<this form>"},
            "action": "Add Contact Tag",
            "tags": [t["tag"] for t in tag_specs],
            "note": "Built AFTER the form exists (needs the form id). Skill 44 "
                    "PLAN-MODE + QC gate (WF-1..21, rubric >= 8.5) applies.",
        },
        "hidden_field_alt": {
            "how": "Add the built-in Tags object-field as a HIDDEN field with a "
                   "preset value; submission writes the tag to the contact.",
            "when": "Only if no workflow is desired; workflow is preferred/testable.",
        },
    }


def _build_form_plan(task: dict, fields: List[dict], dep_plan: dict) -> dict:
    location_id = (task.get("location_id") or task.get("GHL_LOCATION_ID")
                   or os.environ.get("GHL_LOCATION_ID", ""))
    form_name = ensure_zhc_name(task.get("form_name", task.get("title", "New Form")))
    keep_defaults = task.get("keep_default_fields", ["First Name", "Last Name", "Email"])
    delete_defaults = [d for d in DEFAULT_FORM_FIELDS if d not in keep_defaults]
    embed_target = task.get("embed_target", {})  # {type: funnel|website|page, page_id/url}

    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "builder_version": FORM_BUILDER_VERSION,
        "status": "LIVE (runtime snapshot-and-bind field placement; v0.1.0)",
        "location_id": location_id,
        "form_name": form_name,                 # ZHC <name>
        # FAIL-CLOSED rename (v18.1.5): a created form must never proceed (or be
        # left behind) carrying its default name — see the walk's F3 branch.
        "rename_required": bool(task.get("rename_required", True)),
        "start_from": task.get("start_from", "scratch"),  # "scratch" | "template"
        "default_fields_keep": keep_defaults,
        "default_fields_delete": delete_defaults,
        "fields": fields,
        "dependency_plan": dep_plan,            # custom fields + tags (Skill 44)
        "styling": task.get("styling", {
            "themes": task.get("theme"),
            "custom_css": task.get("custom_css", ""),
            "note": "Custom CSS takes precedence over form styling + themes (15:55).",
        }),
        "embed": {
            "capture": ["embed_code_js", "form_link"],
            "target": embed_target,
            "verify": "render_check 200 + snippet tag present in RENDERED DOM "
                      "(ghl_verify.render_check); embed VERBATIM, NO SRI attrs.",
        },
        "model_ladders": {"think": THINK_LADDER, "execute": EXECUTE_LADDER, "qc": QC_LADDER},
        "real_domains": {
            "app_shell": GHL_APP_ORIGIN_DEFAULT,
            "form_builder": f"https://{GHL_FORM_BUILDER_HOST}/form-builder-v2/<formId> "
                            "(RUNTIME SNAPSHOT-GATED — confirm on first live run)",
        },
    }


def _emit_click_list(task: dict, fields: List[dict], plan: dict) -> dict:
    """The full ordered click script handed to the DUMB browser operator."""
    steps: List[dict] = []
    n = 0

    def add(phase: str, action: str, target: str, note: str = "",
            wait: str = "", ts: str = "") -> None:
        nonlocal n
        n += 1
        steps.append({"n": n, "phase": phase, "action": action, "target": target,
                      "wait_for": wait, "note": note, "video_ts": ts})

    loc = plan["location_id"]
    form_name = plan["form_name"]
    app_url = f"{GHL_APP_ORIGIN_DEFAULT}/v2/location/{loc}/dashboard"

    # F1 — navigate to Forms  (00:05–00:56)
    add("F1", "navigate", app_url, "Open app shell (seeded session).", wait="Dashboard", ts="00:05")
    add("F1", "click", "Sites", "Far-left nav → Funnels page loads.", wait="Funnels", ts="00:29")
    add("F1", "click", "Forms", "Top secondary-nav tab (~3/4 across).",
        wait="Create Form", ts="00:47")

    # F2 — create the form  (00:56–01:39)
    add("F2", "click", "Create Form",
        "Blue button, top-right. Fallback label: 'Add Form'.", wait="Start from scratch", ts="00:56")
    if plan["start_from"] == "template":
        add("F2", "click", "Use a template", "Template path (if requested).", ts="01:13")
    else:
        add("F2", "confirm", "Start from scratch", "Leave selected (default).", ts="01:13")
    add("F2", "click", "Create", "Blue Create button at bottom of pop-up → form builder.",
        wait="Form Elements", ts="01:27")

    # F3 — rename the form  (04:22–05:03)
    add("F3", "click", "Form 1", "Default name at top ('Form' + number).", ts="04:22")
    add("F3", "type", form_name, "Type the ZHC-prefixed form name.", ts="04:37")
    add("F3", "press", "Enter", "Commit the form name.", wait=form_name, ts="04:50")

    # F4 — trim default fields  (01:39–02:27)
    for d in plan["default_fields_delete"]:
        add("F4", "delete_field", d, "Remove unneeded default field (hover → trash).", ts="02:00")

    # F5 — standard fields via Quick Add  (05:03–08:16)
    for f in fields:
        if f["source"] != "standard":
            continue
        cat = f["quick_add_category"] or "Personal Info"
        add("F5", "drag", f"{f['element']}  [Form Elements ▸ {cat}]  →  form canvas",
            f"Drag the {f['element']} tile onto the form at its position.",
            wait=f["label"], ts="05:29")
        if f["label"] and f["label"] != f["element"]:
            add("F5", "fill", f"Label = {f['label']!r}", "Right panel → Label.", ts="05:45")
        if f["placeholder"]:
            add("F5", "fill", f"Placeholder = {f['placeholder']!r}", "Right panel → Placeholder.")
        if f["width_pct"] != 100:
            add("F5", "set", f"Field Width = {f['width_pct']}%",
                "Two 50% fields share one row.", ts="06:08")
        if f.get("query_key"):
            add("F5", "fill", f"Query Key = {f['query_key']!r}",
                "URL param — lowercase, no spaces/special.", ts="06:32")
        if f["required"]:
            add("F5", "check", "Required", "Right panel checkbox.", ts="06:08")
        if f["hidden"]:
            add("F5", "check", "Hidden", "Right panel checkbox (not with Required).")

    # F6 — custom fields via Add Object Fields (PRE-CREATED by Skill 44)  (12:14–14:12)
    custom = [f for f in fields if f["source"] == "custom"]
    if custom:
        add("F6", "click", "Add Object Fields",
            "SECOND left-panel tab — NOT Quick Add. Object dropdown must read Contact.",
            wait="Search by Name", ts="12:15")
    for f in custom:
        add("F6", "fill", f"Search by Name = {f['field_key']!r}",
            "Locate the pre-created zhc_ field (created by Skill 44).", ts="12:47")
        add("F6", "drag", f"{f['label']} [{f['field_key']}]  →  form canvas",
            "Drag the pre-created custom field in. Unique key + custom-field name "
            "are LOCKED; only Label is editable.", wait=f["label"], ts="12:56")
        add("F6", "fill", f"Label = {f['label']!r}", "Right panel → Label (client-facing).", ts="13:30")
        # field-type-specific settings (e.g. Rating) — 10:35–12:14
        st = f.get("settings") or {}
        for sk, sv in st.items():
            add("F6", "set", f"{f['field_type']} settings: {sk} = {sv!r}",
                "Field-type-specific setting (e.g. Rating icon/count/store-as).", ts="10:45")
        if f["required"]:
            add("F6", "check", "Required", "Right panel (not with Hidden).", ts="13:36")
        if f["hidden"]:
            add("F6", "check", "Hidden",
                "Use for score/tag/pass-through data (not with Required).", ts="13:43")

    # F7 — save draft  (14:16–14:31)
    add("F7", "click", "Save", "Blue Save, top-right → draft saved.", wait="Saved", ts="14:16")

    # F8 — style the form  (14:26–16:44)
    add("F8", "click", "Styles and Options", "Selector directly under Save.",
        wait="Themes", ts="14:26")
    if plan["styling"].get("themes"):
        add("F8", "click", f"Theme = {plan['styling']['themes']!r}", "Themes tab.", ts="16:19")
    if plan["styling"].get("custom_css"):
        add("F8", "click", "Options", "Deselect any field → form-level Options.", ts="14:57")
        add("F8", "click", "Advanced", "Advanced → Custom CSS box.", ts="15:13")
        add("F8", "fill", "Custom CSS = <plan.styling.custom_css>",
            "Custom CSS OVERRIDES form styling + themes (15:55).", ts="15:55")
    add("F8", "click", "Save", "Save style options.", ts="16:46")

    # F9 — preview  (18:14–18:23)
    add("F9", "click", "Preview", "Top-right → shows how the form displays.", ts="18:14")

    # F10 — Integrate → capture embed code + link  (18:23–18:54)
    add("F10", "click", "Integrate", "Top-right → embed/share/email panel.",
        wait="Copy Embed Code", ts="18:26")
    add("F10", "read", "Copy Embed Code",
        "Capture the JavaScript embed snippet (blue Copy Embed Code).", ts="18:34")
    add("F10", "read", "form link", "Also capture the shareable form link.", ts="18:44")

    # F11 — embed into a GHL page/funnel/website (hand off to page-blob splice)
    tgt = plan["embed"]["target"]
    if tgt:
        add("F11", "handoff", f"embed snippet → {tgt.get('type','page')} {tgt.get('page_id', tgt.get('url',''))}",
            "ghl_rest_canvas code element: paste snippet VERBATIM (no SRI). "
            "Optional CSS wrapper for visual polish. Then ghl_verify.render_check.")

    # F12 — attach tags (Skill 44 workflow; NOT the dumb browser)
    if plan["dependency_plan"]["tags"]:
        add("F12", "handoff",
            "tags → Skill 44 'Form Submitted → Add Contact Tag' workflow",
            "Tags already created (zhc_). Skill 44 builds the attach workflow using "
            "this form's id. Alt: hidden Tags object-field.")

    # F13 — verify
    add("F13", "verify", "form in Forms list under ZHC name + embed renders",
        "render_check 200 + snippet marker in DOM; custom fields/tags re-GET 200.")

    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "form_name": form_name,
        "total_steps": n,
        "dry_run": True,
        "selector_strategy": SELECTOR_STRATEGY,
        "operator_note": (
            "DUMB-BROWSER SCRIPT — execute verbatim. Every target is pre-specified; "
            "make no decisions. Transcript is canonical; video_ts cites the moment. "
            "Custom fields + tags are pre-created by Skill 44 BEFORE this runs."
        ),
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
def _run_preflight(task: dict, fields: List[dict], dep_plan: dict,
                   *, live: bool = False) -> dict:
    """THINK-layer gate. ``live=True`` (the ``--no-dry-run`` path) additionally
    HARD-verifies the runtime environment so a live attempt is never burned on
    an environment mistake (F-P9)."""
    checks: List[dict] = []
    stop: Optional[str] = None

    def chk(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        nonlocal stop
        checks.append({"check": name, "pass": ok, "detail": detail})
        if not ok and hard and stop is None:
            stop = f"{name}: {detail}"

    loc = (task.get("location_id") or task.get("GHL_LOCATION_ID")
           or os.environ.get("GHL_LOCATION_ID") or os.environ.get("GOHIGHLEVEL_LOCATION_ID", "")).strip()
    chk("F-P1:location_id", bool(loc), f"location_id={loc!r}")
    chk("F-P2:location_gate", True, "delegated to dispatcher (no co-mingling)")
    chk("F-P3:spec_present", bool(task.get("form_fields") or task.get("title") or task.get("form_name")),
        "form_fields or title/form_name present")
    # zhc enforcement on every custom field key + tag
    bad_keys = [f["field_key"] for f in fields if f["source"] == "custom" and not is_zhc_field_key(f["field_key"])]
    chk("F-P4:zhc_field_keys", not bad_keys, f"non-zhc keys: {bad_keys}")
    bad_tags = [t["tag"] for t in dep_plan["tags"] if not is_zhc_tag(t["tag"])]
    chk("F-P5:zhc_tags", not bad_tags, f"non-zhc tags: {bad_tags}")
    # form name carries ZHC container prefix
    chk("F-P6:zhc_form_name", ensure_zhc_name(task.get("form_name", "x")).startswith(ZHC_NAME_PREFIX),
        "form name carries 'ZHC ' prefix")
    # custom fields must be add_object_fields (never create-on-the-fly)
    aof = all(f.get("add_via") == "add_object_fields" for f in fields if f["source"] == "custom")
    chk("F-P7:custom_via_object_fields", aof, "all custom fields routed via Add Object Fields")
    # headless guard (soft — only when the real skill module is present)
    if ghl_builder is not None and hasattr(ghl_builder, "headless_guard"):
        try:
            ghl_builder.headless_guard()  # type: ignore[attr-defined]
            chk("F-P8:headless_guard", True, "headless OK")
        except Exception as exc:  # noqa: BLE001
            chk("F-P8:headless_guard", False, str(exc))
    else:
        chk("F-P8:headless_guard", True, "skill module absent (dry-run/review) — deferred to live", hard=False)

    # F-P9 (v18.1.11): Playwright must be importable under THIS interpreter
    # BEFORE a live walk starts. F3 (inline-title rename) and F4 (default-field
    # removal) ride ghl_iframe_drag's Playwright-over-CDP seam; with the wrong
    # `python3` first on PATH (live 2026-07-08: a Homebrew python3.14 WITHOUT
    # Playwright was picked up instead of the interpreter Playwright is
    # installed under) the walk fails DEEP in the build — after a real form
    # already exists — with an opaque `playwright-unavailable`. Fail HERE, with
    # the interpreter named and the fix spelled out, so an environment mistake
    # can never burn a live attempt. Dry-run/THINK keeps working anywhere
    # (soft check, recorded as a warning).
    pw_ok = bool(ghl_iframe_drag is not None
                 and getattr(ghl_iframe_drag, "PLAYWRIGHT_AVAILABLE", False))
    pw_detail = (
        f"Playwright importable under {sys.executable}" if pw_ok else (
            f"Playwright is NOT importable under this interpreter "
            f"({sys.executable}, python {sys.version.split()[0]}). The LIVE "
            "walk requires it: F3 rename + F4 field-removal ride "
            "Playwright-over-CDP (ghl_iframe_drag). Re-run under the "
            "interpreter that HAS Playwright — verify with: "
            "<python3> -c 'import playwright.sync_api' — or install it for "
            f"this one: {sys.executable} -m pip install playwright && "
            f"{sys.executable} -m playwright install chromium. NOTE: a bare "
            "`pip`/`playwright` on PATH may belong to a DIFFERENT python (e.g. "
            "a Homebrew install); always use `<python3> -m pip` / "
            "`<python3> -m playwright` with the same python3 that will run "
            "this tool."))
    if live:
        chk("F-P9:playwright_interpreter", pw_ok, pw_detail)
    else:
        chk("F-P9:playwright_interpreter", True,
            pw_detail if pw_ok else
            f"WARNING (dry-run, soft): {pw_detail}", hard=False)

    out = {"pass": stop is None, "checks": checks, "ts": _ts()}
    if stop:
        out["stop_reason"] = stop
    return out


def _idempotency_key(task: dict) -> str:
    loc = task.get("location_id", task.get("GHL_LOCATION_ID", ""))
    name = task.get("form_name", task.get("title", "form"))
    bh = hashlib.sha256(json.dumps(task.get("form_fields", []), sort_keys=True, default=str).encode()).hexdigest()[:16]
    return hashlib.sha256(f"{loc}:{name}:{bh}".encode()).hexdigest()


# ===========================================================================
# LIVE browser executor — the DUMB / DO layer
# ===========================================================================
# Walks click_list['steps'] via agent-browser (0.27.0) per SELECTORS-LIVE-form.md.
#   • Auth = token-only seed rail (seed-ghl-auth.py mint + inject-ghl-auth.sh
#     seed/activate, KEEP_SESSION so the seeded session stays open for the build).
#     NEVER `open`/`reload` after seeding — the agency whitelabel boot IIFE would
#     firebase.signOut() and bounce to /login. All navigation is SPA $router.push.
#   • Named buttons → role/name anchors (agent-browser resolves visible text/role):
#     Create form · Create · Save · Preview · Integrate · Actions · Delete.
#   • Icon toolbar (+Add element / Styles) → SVG path-`d` signatures — in-iframe,
#     runtime-capture.
#   • In-iframe surfaces (Quick-Add drags, field props, inline title, tabs) are
#     genuine [runtime-capture] (cross-origin iframe, churning CDP refs): snapshot
#     and bind at runtime; on a REQUIRED miss → STOP-and-report (never invent CSS,
#     never brute-force). Cosmetic/optional surfaces (rename, styles) degrade to a
#     recorded warning rather than a hard stop.
# GLUE ONLY: every action is an agent-browser command emitted via
# ghl_builder.browser_cmd; this module never mutates GHL state directly.
# ---------------------------------------------------------------------------


class StopAndReport(RuntimeError):
    """A REQUIRED live surface could not be resolved, or auth failed. STOP — do not
    brute-force. Carries the step + reason for the operator report."""

    def __init__(self, step: str, reason: str):
        self.step = step
        self.reason = reason
        super().__init__(f"STOP@{step}: {reason}")


# ── LOCKED routes (SELECTORS-LIVE-form.md §1) ────────────────────────────────
def _dashboard_route(loc: str) -> str:
    return f"/v2/location/{loc}/dashboard"


def _forms_list_route(loc: str) -> str:
    return f"/v2/location/{loc}/form-builder/main"


def _form_builder_route(loc: str, form_id: str) -> str:
    return f"/v2/location/{loc}/form-builder-v2/{form_id}"


def _canonical_session(location_id: str) -> str:
    """The box-canonical agent-browser session name — MUST match browser_manager.sh
    bm_session_name (ghl-skill6-<loc>, lowercased, [a-z0-9-])."""
    if browser_manager is not None and hasattr(browser_manager, "session_name"):
        try:
            return browser_manager.session_name(location_id)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    raw = f"ghl-skill6-{location_id}".lower()
    raw = re.sub(r"[^a-z0-9-]", "-", raw)
    return re.sub(r"-{2,}", "-", raw).strip("-")


# ── PATH resilience so `agent-browser` is always found ───────────────────────
def _ensure_agent_browser_path(env: dict) -> dict:
    """Guarantee `~/.npm-global/bin` (where the `agent-browser` CLI lives) is on
    `env['PATH']`, at the FRONT, prepending ONLY if it is missing.

    On the operator box, sourcing `~/.openclaw/secrets/.env` can clobber PATH and
    drop `~/.npm-global/bin`, so spawning a browser subprocess fails with
    'command not found'. This is purely defensive — it NEVER reads or touches the
    secrets file; it only repairs the PATH of the env dict handed to a spawn."""
    bindir = os.path.expanduser("~/.npm-global/bin")
    path = env.get("PATH") or os.environ.get("PATH") or os.defpath
    parts = [p for p in path.split(os.pathsep) if p]
    if bindir not in parts:
        env["PATH"] = os.pathsep.join([bindir, *parts]) if parts else bindir
    return env


# ── agent-browser command glue (mirrors ghl_survey_builder._run_cmd) ─────────
def _ab(session: str, *args: str, timeout: int = 30, stdin: Optional[str] = None
        ) -> subprocess.CompletedProcess:
    """Run ONE agent-browser command, headless-forced via ghl_builder.browser_cmd.
    Returns CompletedProcess; never raises (callers inspect returncode/stdout).

    Every arg is shell-quoted BEFORE the browser_cmd join: browser_cmd assembles
    a single command STRING with a plain ' '.join and this glue re-splits it with
    shlex.split, so an unquoted multi-word arg ('Create form', 'Search by Name',
    a screenshot path with spaces) would silently shatter into separate CLI
    tokens and change the command's meaning (proven live 2026-07-07 — part of
    the v18.1.3 text-verb fix). shlex.quote(arg) survives the round-trip as
    exactly ONE argv token; bare flags like '-i' / '--text' are unchanged."""
    cmd_str = ghl_builder.browser_cmd(  # type: ignore[union-attr]
        "--session", session, *(shlex.quote(str(a)) for a in args))
    _log(f"[ab] {cmd_str}")
    env = _ensure_agent_browser_path(dict(os.environ))
    try:
        return subprocess.run(shlex.split(cmd_str), input=stdin, capture_output=True,
                              text=True, timeout=timeout, env=env)
    except Exception as exc:  # noqa: BLE001
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=str(exc))


def _ab_val(cp: subprocess.CompletedProcess) -> str:
    """agent-browser 0.27.0 `eval` returns the JS value JSON-encoded; strip one
    layer of surrounding double-quotes + trailing CR (inject-ghl-auth.sh:543-546)."""
    out = (cp.stdout or "").strip()
    if out.endswith("\r"):
        out = out[:-1]
    if len(out) >= 2 and out[0] == '"' and out[-1] == '"':
        try:
            return json.loads(out)
        except Exception:  # noqa: BLE001
            return out[1:-1]
    return out


def _eval(session: str, js: str, timeout: int = 20) -> str:
    """Evaluate JS via `eval --stdin` (safe for large / quoted payloads)."""
    return _ab_val(_ab(session, "eval", "--stdin", timeout=timeout, stdin=js))


# ── TEXT-targeting verbs (v18.1.3 root-cause fix) ────────────────────────────
# agent-browser 0.27.0 treats a BARE positional on `click` / `fill` / `wait` as
# a CSS selector / XPath / @ref — NEVER a text match (per `agent-browser
# click|fill|wait --help`). So `click "Create form"` and `wait -- "Start from
# Scratch"` could not succeed even with that exact text visibly on the page
# (hermetic data:-URL probe 2026-07-07: bare form → rc=1 'Element not found' /
# wait timeout; `find text "Create form" click` and `wait --text "Start from
# Scratch"` → rc=0). Every text-based interaction below therefore uses the
# CLI's REAL text verbs:
#   wait  --text <text>                  (substring match)
#   find  text <text> click              (visible-text click)
#   find  label|placeholder <x> fill <v> (label-identified fill)
#   keyboard type <text>                 (type into the FOCUSED element)
# This was the actual F2 'Create form' live failure — the click silently never
# happened; the modal/timing hypotheses gated a click that never landed.
def _click(session: str, target: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Click by VISIBLE TEXT via `find text <target> click` (substring match).
    A bare `click <target>` positional is a SELECTOR, not a text match.

    ⚠️ SUBSTRING + first-DOM-order-match: when the target text is a SUBSTRING
    of OTHER on-screen text this can resolve rc=0 against the WRONG element
    (live 2026-07-07, F2 modal confirm — see ``_click_button``). Only use this
    for text that is unambiguous on the live surface at click time."""
    return _ab(session, "find", "text", target, "click", timeout=timeout)


def _click_button(session: str, name: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Click the BUTTON whose ACCESSIBLE NAME is EXACTLY ``name`` via
    `find role button click --name <name> --exact` — the disambiguating form
    for chrome buttons whose label is a SUBSTRING of other on-screen text.

    THE PROVEN COLLISION (live 2026-07-07, F2 create-modal confirm): with the
    'Create new form' modal open, THREE elements carry the text 'Create'
    simultaneously — (1) the page header's '+ Create form' button sitting
    BEHIND the modal overlay, (2) the modal title text 'Create new form',
    (3) the blue confirm button labeled exactly 'Create'. The substring form
    `find text Create click` returned rc=0 having resolved the FIRST DOM-order
    match — the header button — so the SPA never navigated into
    /form-builder-v2/<id> and the id-capture poll timed out (hermetic
    collision probe on the same locator engine: get_by_text('Create') → 3
    matches, first = the header button; role=button + name='Create' +
    exact=True → exactly ONE match, the confirm, and clicking it fired the
    confirm handler).

    WHY THIS FORM IS UNAMBIGUOUS: role=button excludes the modal TITLE (a
    heading/static-text node, not a button); --exact compares the accessible
    name byte-for-byte, so 'Create form' and 'Create new form' both fail the
    equality test. NON-exact --name is still a substring match and would pull
    the header button back in (probe: 2 matches without --exact) — --exact is
    REQUIRED, not decoration. This is SELECTORS-LIVE-form.md §4's LOCKED
    anchor for the confirm, `getByRole('button', { name: 'Create' })` (conf
    9.5), expressed through the CLI (flags per `agent-browser find --help`,
    0.27.0 — the gates.json pin)."""
    return _ab(session, "find", "role", "button", "click",
               "--name", name, "--exact", timeout=timeout)


def _fill(session: str, label: str, value: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Fill the input identified by its VISIBLE LABEL text (aria-label /
    associated <label>), falling back to PLACEHOLDER text (GHL search boxes
    like 'Search by Name' are placeholder-identified). A bare `fill <label>`
    positional is a SELECTOR, so the old form could never bind by label.
    Returns the last attempt's CompletedProcess (rc==0 iff a fill landed)."""
    cp = _ab(session, "find", "label", label, "fill", value, timeout=timeout)
    if cp.returncode != 0:
        cp = _ab(session, "find", "placeholder", label, "fill", value, timeout=timeout)
    return cp


def _wait_text(session: str, text: str, timeout: int = 20) -> subprocess.CompletedProcess:
    """Wait for TEXT to appear via `wait --text <text>` (substring match).
    The previous `wait -- <text>` form parsed <text> as a CSS selector and
    timed out (rc=1) even with the text visibly present."""
    return _ab(session, "wait", "--text", text, timeout=timeout)


def _hover_text(session: str, text: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Hover the element carrying VISIBLE TEXT ``text`` via `find text <t>
    hover` — a REAL Playwright pointer move (`hover` is a documented `find`
    action, agent-browser 0.27.0 `find --help`), so CSS ``:hover`` rules and
    Vue ``mouseenter`` handlers genuinely fire. Used to STIMULATE
    hover-revealed per-row controls (the Forms-list row 'Actions' button,
    SELECTORS-LIVE-form.md §3) — the list-surface analogue of the per-field
    reveal ghl_iframe_drag v1.2.1 re-stimulates in the builder iframe.
    Hermetic data:-page probe 2026-07-08: 0 visible 'Actions' buttons before
    the hover, 1 after; parking the pointer at (0,0) hid it again."""
    return _ab(session, "find", "text", text, "hover", timeout=timeout)


def _park_pointer(session: str) -> subprocess.CompletedProcess:
    """PARK the REAL pointer at the viewport origin (`mouse move 0 0`) so the
    next hover is a genuine re-ENTRY — ``mouseenter`` only fires on a real
    re-entry, and hovering an already-hovered point is a browser NO-OP.
    Mirrors ghl_iframe_drag._rehover_field (v1.2.1)."""
    return _ab(session, "mouse", "move", "0", "0", timeout=10)


def _mouse_click_at(session: str, x: float, y: float) -> bool:
    """REAL-pointer click at viewport coordinates: `mouse move` → `down` →
    `up` (the same trusted-event rail the iframe coordinate-drag rides).
    Returns True only when ALL THREE mouse commands landed rc=0.

    Used ONLY for the nearest-match disambiguated click on a hover-revealed
    row control whose role+name locator CANNOT be trusted with several
    attached matches: hermetic probe 2026-07-08 proved `find role button
    click --name Actions --exact` resolves the FIRST DOM match — which can be
    a HIDDEN 0×0 button belonging to the WRONG row — and still returns rc=0
    with NO click delivered (a silent wrong-target no-op)."""
    for args in (("mouse", "move", f"{x:.0f}", f"{y:.0f}"),
                 ("mouse", "down"), ("mouse", "up")):
        cp = _ab(session, *args, timeout=10)
        if cp.returncode != 0:
            return False
    return True


def _snapshot(session: str, timeout: int = 20) -> str:
    return (_ab(session, "snapshot", "-i", timeout=timeout).stdout or "")


def _pre_phase_check(session: str, keepalive: Any) -> None:
    """F5 uniform keepalive + pre-phase re-mint (mirrors ghl_survey_builder.py's
    helper of the same name — SKILL-6-BULLETPROOF-SPEC-v1 F5). Call once per
    click-list phase transition (never per-step — that would be wasteful
    subprocess overhead for a check that only ever matters on a ~30-45min
    cadence). Both actions are eval-only per D7 — NEVER a navigate/reload:
      1. keepalive.due() — harmless no-op ping so the session never idles out.
      2. remint_if_stale() — F5(b): proactively re-mint the id_token if it is
         already older than the 45min threshold, ahead of a mid-phase 401.
    A no-op (no keepalive instance, no remint helper available) is safe —
    this only ever ADDS resilience, never gates the build.
    """
    if keepalive is not None:
        try:
            if keepalive.due():
                _ab(session, "eval", "true", timeout=5)  # harmless keepalive ping
        except Exception:  # noqa: BLE001
            pass
    if _real_remint_if_stale is not None:
        try:
            _real_remint_if_stale(session)
        except Exception:  # noqa: BLE001 — proactive remint is never allowed to abort a phase
            pass


def _screenshot(session: str, path: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _ab(session, "screenshot", path, timeout=20)
    except Exception as exc:  # noqa: BLE001
        # Best-effort still (control flow unchanged) — but LOG so a missing
        # evidence screenshot is explainable instead of silently vanishing.
        _log(f"screenshot best-effort failed for {path!r}: {exc}")


def _shot(evidence_root: str, n: List[int], phase: str) -> str:
    n[0] += 1
    return os.path.join(evidence_root, "shots", f"{n[0]:03d}-{phase}.png")


# ── FRAME-SCOPED coordinate-drag seam (the cross-origin-iframe FIX) ───────────
# The GHL form builder renders inside a CROSS-ORIGIN iframe; agent-browser 0.27.0
# cannot LOCATE a non-interactive drag-source tile across that boundary (its
# `frame` verb only re-scopes the read-only a11y snapshot; `eval`/`find`/`drag`
# still bind to the top frame — verified live, SELECTORS-LIVE-form.md §7). So the
# DRAG step alone is delegated to the SHARED ghl_iframe_drag primitive, which
# attaches Playwright to THIS SAME already-logged-in agent-browser Chromium over
# CDP and performs a raw interpolated-pointer drag inside the iframe. Everything
# else (auth, nav, clicks, waits, fills, snapshots) stays on agent-browser.
GHL_FORM_IFRAME_SELECTOR = 'iframe[src*="form-builder-v2"]'


def _get_cdp_url(session: str) -> str:
    """Read the CDP websocket endpoint of the live agent-browser session (`get
    cdp-url`) so Playwright can attach to the SAME logged-in Chromium — no second
    browser, no re-login. Routed through the managed `_ab` glue (browser_cmd),
    never a raw spawn. Returns '' if unavailable."""
    return _ab_val(_ab(session, "get", "cdp-url", timeout=15))


def _perform_iframe_drag(session: str, source_text: str, drop_spec: str,
                         *, verify_text: str,
                         iframe_selector: str = GHL_FORM_IFRAME_SELECTOR,
                         source_scroll_hint: str = "") -> dict:
    """Drag ONE builder tile (``source_text``) onto the canvas landmark
    (``drop_spec``) INSIDE the cross-origin builder iframe, verifying that
    ``verify_text`` then appears. ``drop_spec`` is a full locator SPEC passed
    VERBATIM to the primitive (v18.1.9 — e.g. ``role=button:Submit`` per
    SELECTORS §5; a bare string still resolves as visible text). The old
    unconditional ``text=`` wrapping is exactly what made the live 2026-07-08
    drop target ambiguous against the Quick-Add panel's own 'Submit' texts.
    ``source_scroll_hint`` (the tile's Quick-Add CATEGORY header text, e.g.
    ``"Address"`` for ``City``) lets the primitive scroll a below-the-fold panel
    section into view before locating the tile — the general fix for the live
    2026-07-07 ``F5.locate:City`` miss, for ANY field in ANY category.
    FAIL-CLOSED: raises StopAndReport (not a fake success) when the shared
    primitive is unavailable, the CDP url can't be read, or the
    locate/scroll/drag/verify does not land. This is the seam that replaces the
    top-frame-only ``_ab(session, "drag", ...)`` (which cannot reach the tile)."""
    if ghl_iframe_drag is None:
        raise StopAndReport(
            "iframe-drag.dep",
            "the shared frame-scoped coordinate-drag primitive (ghl_iframe_drag) is not "
            "importable, and agent-browser 0.27.0 alone CANNOT locate a non-interactive "
            "tile across the cross-origin builder iframe. Ship ghl_iframe_drag.py + "
            "Playwright (scoped to Skill 6) — STOP, do not brute-force a top-frame drag.")
    cdp_url = _get_cdp_url(session)
    if not cdp_url:
        raise StopAndReport(
            "iframe-drag.cdp",
            "could not read the agent-browser session's CDP url (`get cdp-url`) to hand "
            "the drag off to Playwright on the SAME logged-in Chromium. STOP.")
    try:
        return ghl_iframe_drag.coordinate_drag(  # type: ignore[union-attr]
            cdp_url,
            iframe_selector=iframe_selector,
            source=f"text={source_text}",
            target=drop_spec,
            url_marker="form-builder",
            verify_text=verify_text,
            source_scroll_hint=(f"text={source_scroll_hint}" if source_scroll_hint else None),
        )
    except ghl_iframe_drag.IframeDragError as exc:  # type: ignore[union-attr]
        # P3-04 (c)4: `.step` stays the EXACT "iframe-drag:<code>" form other
        # code keys on (_DRAG_LOCATE_MISS_STEPS, the selftest at ~2903) — only
        # `.reason` is enriched, to the CC-taxonomy-classified, frame-origin-
        # tagged note (SELECTOR-MISS/VERIFY-FAIL) instead of the bare
        # ``exc.reason`` — so a future board wiring for this builder gets the
        # same diagnosable-card text the survey builder already produces.
        reason = ghl_iframe_drag.board_note(  # type: ignore[union-attr]
            exc, iframe_selector=iframe_selector)
        raise StopAndReport(f"iframe-drag:{exc.code}", reason) from exc


def _perform_iframe_field_remove(session: str, field_spec: str,
                                 *, iframe_selector: str = GHL_FORM_IFRAME_SELECTOR) -> dict:
    """Remove ONE canvas field (``field_spec`` = its DOCUMENTED anchor, SELECTORS
    §6) INSIDE the cross-origin builder iframe via the shared frame-scoped
    primitive (v1.3.0 tiered acquisition: documented specs → broad name/attr
    scans → geometric icon-pill ladder → count-decrease proof). Same dep/CDP
    fail-closed shell as the drag seam; an already-absent field returns a
    truthful idempotent no-op receipt. A primitive failure's RICH diagnostics
    (``IframeDragError.details``) ride along on the raised ``StopAndReport`` so
    the F4 caller can persist them as an evidence receipt."""
    if ghl_iframe_drag is None:
        raise StopAndReport(
            "iframe-remove.dep",
            "the shared frame-scoped primitive (ghl_iframe_drag) is not importable, and "
            "agent-browser 0.27.0 alone CANNOT reach the per-field controls across the "
            "cross-origin builder iframe. Ship ghl_iframe_drag.py + Playwright (scoped "
            "to Skill 6) — STOP, do not brute-force.")
    cdp_url = _get_cdp_url(session)
    if not cdp_url:
        raise StopAndReport(
            "iframe-remove.cdp",
            "could not read the agent-browser session's CDP url (`get cdp-url`) to hand "
            "the field removal off to Playwright on the SAME logged-in Chromium. STOP.")
    try:
        return ghl_iframe_drag.remove_canvas_field(  # type: ignore[union-attr]
            cdp_url,
            iframe_selector=iframe_selector,
            field=field_spec,
            url_marker="form-builder",
        )
    except ghl_iframe_drag.IframeDragError as exc:  # type: ignore[union-attr]
        # P3-04 (c)4: `.reason` carries the CC-taxonomy-classified, frame-
        # origin-tagged note (see _perform_iframe_drag above); `.details`
        # (rich diagnostics) still rides along unchanged.
        reason = ghl_iframe_drag.board_note(  # type: ignore[union-attr]
            exc, iframe_selector=iframe_selector)
        sr = StopAndReport(f"iframe-remove:{exc.code}", reason)
        sr.details = getattr(exc, "details", None)   # rich diagnostics ride along
        raise sr from exc


# ── FRAME-SCOPED CLICK (B-U16 item 2) — the click counterpart to the drag/
# remove seams above, replacing the two best-effort `[runtime-capture]`
# property-panel/tab sites named in references/iframe-drag-capability.md's
# audit ("extend with a frame_click helper"): _bind_field_props's Required/
# Hidden checkbox binds and _ensure_quick_add_panel's Quick-Add TAB switch.
def _perform_frame_click(session: str, target_spec: str, *,
                         iframe_selector: str = GHL_FORM_IFRAME_SELECTOR,
                         verify_text: Optional[str] = None,
                         verify_absent: bool = False) -> dict:
    """Click ONE control (`target_spec`) INSIDE the cross-origin builder iframe
    via the shared frame-scoped primitive (``ghl_iframe_drag.frame_click`` —
    B-U16 item 2), the click counterpart to ``_perform_iframe_drag`` above.
    Same dep/CDP fail-closed shell; CALLERS decide whether a failure here is
    fatal (required surface) or a recorded warning (cosmetic — property-panel
    binds, tab switches both fall in the cosmetic bucket today). FAIL-CLOSED:
    raises StopAndReport (never a fake success) when the shared primitive is
    unavailable, the CDP url can't be read, or the click/verify does not
    land."""
    if ghl_iframe_drag is None:
        raise StopAndReport(
            "frame-click.dep",
            "the shared frame-scoped primitive (ghl_iframe_drag) is not "
            "importable, and agent-browser 0.27.0 alone cannot reliably reach "
            "every non-ref-clickable control across the cross-origin builder "
            "iframe. Ship ghl_iframe_drag.py + Playwright (scoped to Skill 6) "
            "— STOP, do not brute-force.")
    cdp_url = _get_cdp_url(session)
    if not cdp_url:
        raise StopAndReport(
            "frame-click.cdp",
            "could not read the agent-browser session's CDP url (`get cdp-url`) "
            "to hand the click off to Playwright on the SAME logged-in "
            "Chromium. STOP.")
    try:
        return ghl_iframe_drag.frame_click(  # type: ignore[union-attr]
            cdp_url,
            iframe_selector=iframe_selector,
            target=target_spec,
            url_marker="form-builder",
            verify_text=verify_text,
            verify_absent=verify_absent,
        )
    except ghl_iframe_drag.IframeDragError as exc:  # type: ignore[union-attr]
        reason = ghl_iframe_drag.board_note(  # type: ignore[union-attr]
            exc, iframe_selector=iframe_selector)
        raise StopAndReport(f"frame-click:{exc.code}", reason) from exc


def _click_property_checkbox(session: str, text: str, warnings: List[str],
                             tag: str) -> None:
    """Click a property-panel checkbox (Required/Hidden — SELECTORS-LIVE-
    form.md §10) EXACTLY ONCE: via the frame-scoped primitive when available
    (real cross-origin reach, replacing the prior top-frame-only best-effort
    attempt), else the existing agent-browser click. NEVER both — a checkbox
    is a TOGGLE, so clicking it twice would silently undo the very state this
    function is trying to set. A frame-click miss degrades to a recorded
    WARNING and the top-frame fallback, never a hard stop (cosmetic/optional
    surface, same doctrine as the Label bind above)."""
    if ghl_iframe_drag is not None:
        try:
            _perform_frame_click(session, f"text={text}")
            return
        except StopAndReport as sr:
            warnings.append(f"{tag!r}: {text} checkbox frame-click miss "
                            f"({sr.step}) — falling back to the top-frame click")
    _click(session, text)


# ── in-SPA navigation — $router.push ONLY (never open/reload) ────────────────
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


def _router_push(session: str, path: str, expect_contains: str = "") -> str:
    res = _eval(session, _ROUTER_PUSH_JS % json.dumps(path), timeout=25)
    if "NO-ROUTER" in res:
        raise StopAndReport("router.push", f"SPA store/router not mounted for push to {path!r}")
    if expect_contains and expect_contains not in res:
        loc = _eval(session, "location.pathname", timeout=10)
        if expect_contains not in (loc or ""):
            raise StopAndReport(
                "router.push",
                f"pushed to {path!r} but landed at {(res or loc)!r} "
                f"(expected to contain {expect_contains!r})")
    return res


_LOGIN_CHECK_JS = (
    "(() => {"
    "  const pwd = !!document.querySelector('input[type=password]');"
    "  const onLogin = /[?&]logout=true/.test(location.href) || /\\/login(\\b|$)/.test(location.pathname) || pwd;"
    "  return (onLogin ? 'login:' : 'app:') + location.pathname;"
    "})()"
)


def _assert_logged_in(session: str) -> str:
    res = _eval(session, _LOGIN_CHECK_JS, timeout=15)
    if not res.startswith("app:"):
        raise StopAndReport(
            "auth",
            f"session is NOT logged in ({res or 'no-response'}); the token seed did not "
            "establish a session. NO UI-login / 2FA fallback exists — re-grab a fresh "
            "refresh token (Token Grabber) and retry.")
    return res


# ── token-only seed rail ─────────────────────────────────────────────────────
def _seed_and_land(session: str, location_id: str, evidence_root: str) -> dict:
    """Mint (seed-ghl-auth.py) → seed+activate (inject-ghl-auth.sh, KEEP_SESSION) →
    land logged-in at the dashboard via the SPA router (no reload). STOP-and-report
    on any auth failure; never opens the Sign-in form."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    seed_dir = os.path.join(evidence_root, "auth")
    os.makedirs(seed_dir, exist_ok=True)
    seed_file = os.path.join(seed_dir, "ghl-auth-seed.json")

    env = _ensure_agent_browser_path(dict(os.environ))
    env["GHL_LOCATION_ID"] = location_id            # canonical session-name driver
    env["GHL_INJECT_KEEP_SESSION"] = "1"            # leave the seeded session OPEN
    env["GHL_ACTIVATE_PATH"] = _dashboard_route(location_id)

    # LEAK-SAFE: --out ONLY (writes the seed to a chmod-600 file); NEVER --print-seed
    # (that echoes the live id_token + refresh_token to stdout). With --out alone
    # seed-ghl-auth.py mints + writes the file and prints NOTHING sensitive.
    mint = subprocess.run(
        [sys.executable, os.path.join(tools_dir, "seed-ghl-auth.py"),
         "--out", seed_file],
        capture_output=True, text=True, timeout=90, env=env)
    if mint.returncode != 0:
        why = {2: "no usable refresh token", 3: "refresh token revoked/expired"}.get(
            mint.returncode, "mint failed")
        raise StopAndReport("auth.mint",
                            f"seed-ghl-auth.py exit {mint.returncode} ({why}). Token-seed is the "
                            "ONLY auth path — re-grab a fresh refresh token; do NOT open a login form.")

    inject = subprocess.run(
        ["bash", os.path.join(tools_dir, "inject-ghl-auth.sh"), session, seed_file, "--pre-open"],
        capture_output=True, text=True, timeout=200, env=env)
    if inject.returncode != 0:
        raise StopAndReport("auth.seed",
                            f"inject-ghl-auth.sh exit {inject.returncode}: "
                            f"{(inject.stderr or '').strip()[-300:]}")

    landed = _assert_logged_in(session)
    return {"seed_file": seed_file, "landed": landed,
            "inject_tail": (inject.stdout or "").strip()[-160:]}


def _close_session(location_id: str) -> None:
    """Close + state-clear the canonical session (browser_manager.sh teardown verb) —
    no orphan Chromium/engine, no residual seeded state."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    env = _ensure_agent_browser_path(dict(os.environ))
    env["GHL_LOCATION_ID"] = location_id
    try:
        subprocess.run(["bash", os.path.join(tools_dir, "browser_manager.sh"), "teardown"],
                       capture_output=True, text=True, timeout=40, env=env)
    except Exception as exc:  # noqa: BLE001
        _log(f"session close best-effort failed: {exc}")


# ── in-builder captures ──────────────────────────────────────────────────────
# The GHL form builder renders inside a CROSS-ORIGIN iframe at
# `leadgen-apps-form-survey-builder.leadconnectorhq.com/form-builder-v2/<formId>`
# (GHL_FORM_BUILDER_HOST above; SELECTORS-LIVE-form.md §5/§7). An iframe's `.src`
# ATTRIBUTE is readable from the parent even cross-origin — only `contentWindow`/
# `contentDocument` are blocked by same-origin policy — so the form id lives THERE,
# NOT in the top-frame `location.pathname`. Enumerate iframes by DOM (never an
# invented selector), match the first `/form-builder-v2/<id>` src, then FALL BACK to
# the top-frame path/hash/search (preserves the prior behavior).
_FORM_ID_CAPTURE_JS = (
    "(() => {"
    "  const RE = /\\/form-builder-v2\\/([^/?#]+)/;"
    "  for (const f of document.querySelectorAll('iframe')) {"
    "    const src = f.src || f.getAttribute('src') || '';"
    "    const m = src.match(RE);"
    "    if (m) return m[1];"
    "  }"
    "  const top = (location.pathname || '') + (location.hash || '') + (location.search || '');"
    "  const tm = top.match(RE);"
    "  return tm ? tm[1] : '';"
    "})()"
)


# SERVER-SIDE SHAPE GATE for a captured form id. A real GHL form id is an opaque
# ~20-char alphanumeric token (e.g. "cuPqQhLbk0GKeguEbGYW"). We NEVER trust raw eval
# output as an id: a stray path segment, an oversized DOM blob, or any punctuation is
# not a form id. Conservative bound: 15-30 chars, [A-Za-z0-9] only (fullmatch).
_FORM_ID_SHAPE_RE = re.compile(r"[A-Za-z0-9]{15,30}")

# POLL WINDOW for the id capture. After the create-modal `Create` click the SPA
# transitions to `/form-builder-v2/<id>` and MOUNTS the builder iframe
# asynchronously — on a slow, form-heavy account the iframe element/src can lag
# the "Save" chrome by several seconds (live 2026-07-07: a single-shot read here
# raced that mount and returned '' → false F2.create STOP). Poll-with-deadline,
# never a fixed sleep — same pattern as ghl_iframe_drag._verify_placed.
_FORM_ID_CAPTURE_TIMEOUT_S = 15.0
_FORM_ID_CAPTURE_POLL_S = 0.5


def _capture_form_id(session: str, timeout_s: Optional[float] = None,
                     poll_s: Optional[float] = None) -> str:
    """Capture the built form's id from the builder IFRAME's `.src` attribute.

    Reads the form id out of the cross-origin `/form-builder-v2/<formId>` iframe src
    (parent-readable), falling back to the top-frame `location.pathname + hash +
    search` match; returns '' if neither yields an id. Fixes the prior top-frame-only
    read that always returned '' (the top frame carries no form id), which left the
    id uncaptured so downstream delete/verify could not target the form.

    POLLING (the live 2026-07-07 fix): the old single-shot read raced the SPA's
    builder-route transition — the "Save" wait can resolve (or silently time out)
    BEFORE the iframe exists / its src carries `/form-builder-v2/<id>`, so one eval
    returned '' forever. Now the capture re-evaluates on a deadline
    (``_FORM_ID_CAPTURE_TIMEOUT_S``, checking every ``_FORM_ID_CAPTURE_POLL_S``),
    returning the id as soon as one attempt clears the shape gate and returning ''
    cleanly at the deadline (bounded — never hangs). Always makes at least ONE
    attempt, even with a zero/negative budget.

    HARDENING: each raw `_eval` result is re-validated SERVER-SIDE against the GHL
    form-id shape (``[A-Za-z0-9]{15,30}``) before being returned. A value that does
    not match that shape is rejected — never trust raw eval output as an id, so a
    malformed / oversized / punctuation-bearing capture can't poison the downstream
    delete/verify targeting."""
    budget = _FORM_ID_CAPTURE_TIMEOUT_S if timeout_s is None else timeout_s
    pause = _FORM_ID_CAPTURE_POLL_S if poll_s is None else poll_s
    deadline = time.monotonic() + max(0.0, budget)
    while True:
        got = _eval(session, _FORM_ID_CAPTURE_JS, timeout=12)
        form_id = (got or "").strip()
        # Re-validate the captured id's SHAPE before trusting it downstream.
        if _FORM_ID_SHAPE_RE.fullmatch(form_id):
            return form_id
        if time.monotonic() >= deadline:
            return ""
        time.sleep(max(0.0, pause))


# On a capture miss we STOP — but the report must carry EVIDENCE of where the
# browser actually was (live 2026-07-07: the old bare message hid that the walk
# had never left the forms LIST — the create modal never opened — so the failure
# read as an iframe-src bug two steps downstream). Top-frame path + iframe srcs
# (truncated) are exactly the two surfaces the capture JS reads.
_ENTRY_DIAG_JS = (
    "(() => {"
    "  const ifr = Array.from(document.querySelectorAll('iframe'))"
    "    .map(f => (f.src || f.getAttribute('src') || '').slice(0, 120));"
    "  return JSON.stringify({path: (location.pathname || '').slice(0, 160),"
    "                         iframes: ifr.slice(0, 6)});"
    "})()"
)


def _capture_entry_diag(session: str) -> str:
    """Best-effort one-shot page-state evidence for a capture-miss StopAndReport:
    top-frame path + up-to-6 truncated iframe srcs. Never raises; '' on failure."""
    try:
        return (_eval(session, _ENTRY_DIAG_JS, timeout=10) or "").strip()[:600]
    except Exception:  # noqa: BLE001
        return ""


# POLL WINDOW for a text-appears wait, same doctrine as _FORM_ID_CAPTURE_TIMEOUT_S
# above: poll-with-deadline, never trust one opaque single-shot call.
#
# live 2026-07-07 (follow-up to the poll-with-deadline fix above): a SINGLE
# `_wait_text(session, text, timeout=N)` call does NOT actually get an N-second
# budget from agent-browser. The Python `timeout=` kwarg is ONLY the
# subprocess-level kill switch (see `_ab`); it is never forwarded to the CLI as
# a `--timeout` (there is no generic per-call `--timeout` flag — confirmed
# against `agent-browser --help`). The REAL wait duration agent-browser itself
# uses is its own `AGENT_BROWSER_DEFAULT_TIMEOUT` (default 25000ms), entirely
# outside this file's control. F2's create-modal wait passed timeout=20 —
# SHORTER than agent-browser's own 25s default — so the Python watchdog could
# silently force-kill the wait subprocess up to 5s BEFORE agent-browser's own
# native wait would have elapsed, on exactly the step (a cross-origin SPA
# modal transition) most likely to need the full window on a slow,
# form-heavy real account. Poll short, bounded sub-waits against OUR OWN
# monotonic deadline instead of trusting one single-shot call to honor a
# budget it never actually receives.
_TEXT_WAIT_TIMEOUT_S = 20.0
_TEXT_WAIT_SUBCALL_S = 4.0
_TEXT_WAIT_POLL_S = 0.5


def _wait_text_polling(session: str, text: str, timeout_s: Optional[float] = None,
                       subcall_s: Optional[float] = None,
                       poll_s: Optional[float] = None) -> bool:
    """POLL for ``text`` to appear, on a monotonic deadline, via short repeated
    ``_wait_text`` sub-calls — never one long single-shot wait whose real
    duration is entangled with agent-browser's own opaque default action
    timeout (see module notes above ``_TEXT_WAIT_TIMEOUT_S``). Returns True as
    soon as one sub-call reports success; returns False cleanly at the
    deadline (bounded — never hangs). Always makes at least one attempt, even
    with a zero/negative budget (mirrors ``_capture_form_id``)."""
    budget = _TEXT_WAIT_TIMEOUT_S if timeout_s is None else timeout_s
    sub = _TEXT_WAIT_SUBCALL_S if subcall_s is None else subcall_s
    pause = _TEXT_WAIT_POLL_S if poll_s is None else poll_s
    deadline = time.monotonic() + max(0.0, budget)
    while True:
        if _wait_text(session, text, timeout=max(1, int(round(sub)))).returncode == 0:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(max(0.0, pause))


_EMBED_CAPTURE_JS = (
    "(() => {"
    "  const pick = (root) => {"
    "    const ta = root.querySelector('textarea');"
    "    if (ta && ta.value && /<script|<iframe|leadconnector|form/i.test(ta.value)) return ta.value;"
    "    const code = root.querySelector('code, pre');"
    "    if (code && code.textContent && /<script|<iframe|leadconnector|form/i.test(code.textContent)) return code.textContent;"
    "    return '';"
    "  };"
    "  let s = pick(document);"
    "  if (!s) { for (const f of document.querySelectorAll('iframe')) { try { const d = f.contentDocument; if (d) { s = pick(d); if (s) break; } } catch (e) {} } }"
    "  return s || '';"
    "})()"
)


def _capture_embed(session: str) -> str:
    return _eval(session, _EMBED_CAPTURE_JS, timeout=20)


def _capture_form_link(session: str) -> str:
    js = ("(() => { const h = Array.from(document.querySelectorAll('a[href],input'))"
          ".map(e => (e.href || e.value || '')).find(u => /widget\\/form\\//.test(u)); return h || ''; })()")
    return _eval(session, js, timeout=12) or ""


def _xpath_text(text: str) -> str:
    """An XPath selector matching an element whose own text node equals ``text``
    — the text-target form for verbs `find` has no action for (e.g. dblclick):
    agent-browser selectors are CSS / XPath / @ref only, and CSS cannot match
    text. Quote-safe via XPath concat() when ``text`` carries both quote kinds."""
    if '"' not in text:
        lit = f'"{text}"'
    elif "'" not in text:
        lit = f"'{text}'"
    else:
        lit = "concat(" + ",'\"',".join(f'"{p}"' for p in text.split('"')) + ")"
    return f"//*[normalize-space(text())={lit}]"


def _rename_form_title(session: str, form_name: str) -> dict:
    """FRAME-SCOPED rename of the in-iframe inline title (the F3 fix, v18.1.5).

    The title ("Form <n>") lives INSIDE the cross-origin builder iframe and is an
    inline-edit surface — the old top-frame ``dblclick <xpath>`` + ``keyboard
    type`` walk could never reach it and FAILED SILENTLY (live 2026-07-07: a real
    form stayed default-named, so cleanup's name search never found it — the
    orphan hazard this fix removes). The rename now rides the SAME proven
    Playwright-over-CDP seam as the drag (``ghl_iframe_drag.set_inline_title``):
    pattern-locate the title (the default number is unknowable), click into edit
    mode (VERIFIED — an editable must take focus), select-all + type + Enter,
    then VERIFY the new text inside the iframe.

    Returns ``{"renamed", "actual_title", "old_title", "reason"}`` — NEVER raises.
    ``actual_title`` is the name the form is POSITIVELY known to carry afterwards
    (the new name on success; the read-back current title on failure; '' when even
    the read-back failed) so cleanup can target the form by the name it ACTUALLY
    has, not the name we intended."""
    out = {"renamed": False, "actual_title": "", "old_title": "", "reason": ""}
    if ghl_iframe_drag is None:
        out["reason"] = ("the shared frame-scoped primitive (ghl_iframe_drag) is not "
                         "importable — the in-iframe title cannot be reached")
        return out
    cdp_url = _get_cdp_url(session)
    if not cdp_url:
        out["reason"] = "could not read the session CDP url (`get cdp-url`)"
        return out
    try:
        rec = ghl_iframe_drag.set_inline_title(  # type: ignore[union-attr]
            cdp_url,
            iframe_selector=GHL_FORM_IFRAME_SELECTOR,
            new_title=form_name,
            title_specs=ghl_iframe_drag.DEFAULT_FORM_TITLE_SPECS,  # type: ignore[union-attr]
            url_marker="form-builder",
        )
        out.update(renamed=True, actual_title=form_name,
                   old_title=rec.get("old_title", ""))
        return out
    except ghl_iframe_drag.IframeDragError as exc:  # type: ignore[union-attr]
        # P3-04 (c)4: same CC-taxonomy classification, frame-origin tagged —
        # this function's "never raises" contract is unchanged, only the
        # reason text carries the diagnosable prefix now.
        out["reason"] = ghl_iframe_drag.board_note(  # type: ignore[union-attr]
            exc, iframe_selector=GHL_FORM_IFRAME_SELECTOR)
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"{type(exc).__name__}: {exc}"
    # Rename failed → READ BACK the title the form ACTUALLY carries so cleanup can
    # still positively target it (idempotency: an already-renamed form reads back
    # as the target name → treat as renamed).
    try:
        specs = (f"exact={form_name}",) + tuple(
            ghl_iframe_drag.DEFAULT_FORM_TITLE_SPECS)  # type: ignore[union-attr]
        rd = ghl_iframe_drag.read_inline_title(  # type: ignore[union-attr]
            cdp_url, iframe_selector=GHL_FORM_IFRAME_SELECTOR,
            title_specs=specs, url_marker="form-builder")
        out["actual_title"] = rd.get("title", "")
        if out["actual_title"] == form_name:
            out["renamed"] = True
            out["reason"] = f"already carries the target name ({out['reason']})"
    except Exception as exc:  # noqa: BLE001
        out["reason"] += f"; title read-back also failed ({type(exc).__name__})"
    return out


def _click_menuitem(session: str, name: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Click the MENUITEM whose accessible name is EXACTLY ``name`` —
    SELECTORS-LIVE-form.md §3's locked anchor for the row-Actions menu items
    (`getByRole('menuitem', { name })`, conf 9.5), expressed through the CLI.
    Role-scoped + --exact so the menu 'Delete' can never collide with the
    confirm dialog's 'Delete' BUTTON (or any other on-screen 'Delete' text)."""
    return _ab(session, "find", "role", "menuitem", "click",
               "--name", name, "--exact", timeout=timeout)


# ── POSITIVE list-evidence (cleanup verification, v18.1.5) ────────────────────
# The forms LIST is a TOP-FRAME surface (SELECTORS-LIVE-form.md §3), so its DOM
# is directly evaluable. These reads are EVIDENCE-GATHERING (like
# _FORM_ID_CAPTURE_JS / _ENTRY_DIAG_JS), never invented click selectors.
#
# WHY NOT the a11y snapshot: the search TEXTBOX echoes the queried name (an input
# value can appear in the snapshot), so `name in snapshot` is satisfiable by the
# search box ALONE — exactly the class of false evidence that let the live
# 2026-07-07 cleanup claim success. Leaf-node textContent === name counts only
# RENDERED text (row titles); an input's value is not textContent.
_LEAF_COUNT_JS = (
    "(() => {"
    "  const q = %s;"
    "  let n = 0;"
    "  for (const el of document.querySelectorAll('body *')) {"
    "    if (el.childElementCount === 0 && (el.textContent || '').trim() === q) n++;"
    "  }"
    "  return String(n);"
    "})()"
)

# One evidence pass over the rendered Forms list for the ROW-'Actions' control
# (v18.1.11 — the hover-reveal fix): how many 'Actions' buttons are ATTACHED to
# the DOM, how many are VISIBLE (non-zero client rect + not visibility:hidden),
# and the viewport CENTER of the visible one NEAREST the matched row title's
# leaf — a per-row control belongs to its own row (the top-frame analogue of
# ghl_iframe_drag._nearest_visible_match, v1.2.1). Same evidence-not-selector
# doctrine as _LEAF_COUNT_JS above.
_ACTIONS_PROBE_JS = (
    "(() => {"
    "  const q = %s;"
    "  let ref = null;"
    "  for (const el of document.querySelectorAll('body *')) {"
    "    if (el.childElementCount === 0 && (el.textContent || '').trim() === q) {"
    "      ref = el; break;"
    "    }"
    "  }"
    "  const btns = Array.from(document.querySelectorAll('button'))"
    "    .filter(b => (b.textContent || '').trim() === 'Actions');"
    "  const vis = btns.filter(b => {"
    "    const r = b.getBoundingClientRect();"
    "    return r.width > 0 && r.height > 0"
    "      && getComputedStyle(b).visibility !== 'hidden';"
    "  });"
    "  const center = (el) => { const r = el.getBoundingClientRect();"
    "    return [r.x + r.width / 2, r.y + r.height / 2]; };"
    "  let best = null, bestD = Infinity;"
    "  if (ref && vis.length) {"
    "    const [rx, ry] = center(ref);"
    "    for (const b of vis) {"
    "      const [cx, cy] = center(b);"
    "      const d = (cx - rx) ** 2 + (cy - ry) ** 2;"
    "      if (d < bestD) { bestD = d; best = [cx, cy]; }"
    "    }"
    "  } else if (vis.length) { best = center(vis[0]); }"
    "  return JSON.stringify({attached: btns.length, visible: vis.length,"
    "                         x: best ? best[0] : -1, y: best ? best[1] : -1});"
    "})()"
)


def _eval_leaf_count(session: str, text: str) -> int:
    """Count RENDERED leaf elements whose exact trimmed text equals ``text``.
    Returns -1 when the count could not be evaluated — callers must treat -1 as
    UNKNOWN (fail-closed), never as zero."""
    try:
        raw = _eval(session, _LEAF_COUNT_JS % json.dumps(text), timeout=12)
        return int((raw or "").strip())
    except Exception:  # noqa: BLE001
        return -1


def _probe_row_actions(session: str, row_title: str) -> Dict[str, Any]:
    """Evaluate _ACTIONS_PROBE_JS once. Returns {attached, visible, x, y};
    attached/visible == -1 means UNKNOWN (unevaluable) — callers must treat
    -1 as fail-closed, NEVER as zero and NEVER as revealed."""
    out: Dict[str, Any] = {"attached": -1, "visible": -1, "x": -1.0, "y": -1.0}
    try:
        raw = _eval(session, _ACTIONS_PROBE_JS % json.dumps(row_title), timeout=12)
        d = json.loads((raw or "").strip())
        out["attached"] = int(d.get("attached", -1))
        out["visible"] = int(d.get("visible", -1))
        out["x"] = float(d.get("x", -1.0))
        out["y"] = float(d.get("y", -1.0))
    except Exception:  # noqa: BLE001
        pass
    return out


# Reveal-poll budget for the hover-revealed row 'Actions' control — same
# poll-with-re-stimulation shape as ghl_iframe_drag's remove-control poll
# (_REMOVE_POLL_S / _REMOVE_REHOVER_EVERY_S, v1.2.1), sized for a top-frame
# list row (each evidence pass is a full `eval` subprocess round-trip).
_ACTIONS_REVEAL_TIMEOUT_S = 12.0    # total budget before failing closed
_ACTIONS_REVEAL_POLL_S = 0.5        # pause between evidence passes
_ACTIONS_REHOVER_EVERY_S = 2.0      # park-away + re-enter cadence


def _reveal_row_actions(session: str, row_title: str) -> Dict[str, Any]:
    """Hover the matched row and POLL (monotonic deadline) until its
    hover-revealed 'Actions' button is VISIBLE.

    THE BUG THIS KILLS (live 2026-07-08, cleanup attempt): the Forms-list row
    'Actions' button is HOVER-REVEALED — exactly one row title matched but
    ZERO 'Actions' buttons existed in the DOM, so the old SINGLE
    count-evaluation refused the click and cleanup silently failed to delete
    the form. One peek at a hover-revealed control is exactly the class of
    bug the v18.1.10 F4 remove-control fix killed inside the builder iframe;
    this is the same fix on the list surface: hover first, then poll, and on
    a cadence PARK the pointer off the row and re-enter it (``mouseenter``
    only fires on a REAL re-entry — hovering an already-hovered point is a
    browser NO-OP).

    Returns the LAST probe (attached/visible/x/y) plus
    {'revealed': bool, 'hover_cycles': n}. NEVER raises; NEVER clicks —
    the deadline miss stays fail-closed in the caller."""
    _hover_text(session, row_title)
    hover_cycles = 1
    deadline = time.monotonic() + _ACTIONS_REVEAL_TIMEOUT_S
    next_rehover = time.monotonic() + _ACTIONS_REHOVER_EVERY_S
    while True:
        probe = _probe_row_actions(session, row_title)
        if probe["visible"] > 0:
            probe["revealed"] = True
            probe["hover_cycles"] = hover_cycles
            return probe
        now = time.monotonic()
        if now >= deadline:
            probe["revealed"] = False
            probe["hover_cycles"] = hover_cycles
            return probe
        if now >= next_rehover:
            _park_pointer(session)
            _hover_text(session, row_title)
            hover_cycles += 1
            next_rehover = time.monotonic() + _ACTIONS_REHOVER_EVERY_S
        time.sleep(_ACTIONS_REVEAL_POLL_S)


# ── cleanup: DELETE the built form + POSITIVELY VERIFY it is gone ─────────────
# (SELECTORS-LIVE-form.md §3 anchors; v18.1.5 overhaul)
#
# THE OLD BUG (live 2026-07-07): cleanup searched for the INTENDED name, found
# nothing (the rename had silently failed, so the real form still carried its
# default "Form <n>" name), ignored every click rc, saw no residue FOR THAT NAME,
# and reported deleted=true — while a real, live form sat in the account. Every
# step below is now rc-checked and the outcome is POSITIVELY verified
# (present-before → delete → absent-after, on RENDERED leaf text); anything
# unverifiable returns deleted=False with the evidence, never an assumption.
def _delete_form(session: str, location_id: str, form_id: str, form_name: str,
                 actual_title: str = "") -> dict:
    """Delete the built form from the Forms list and POSITIVELY verify deletion.

    search (actual title first — the name the form REALLY carries, captured by
    the F3 rename receipt) → require EXACTLY ONE matching row title → HOVER the
    row and POLL for its hover-revealed 'Actions' button (v18.1.11 — never one
    peek; park-away + re-hover on a cadence, same doctrine as the F4
    remove-control poll) → click it (role-exact when it is the ONLY attached
    'Actions' button; otherwise a REAL-pointer click on the visible one NEAREST
    the matched row — never the wrong row) → menuitem Delete (role-scoped) →
    confirm dialog Delete (role button, exact) → POLL the re-searched list
    until ZERO rendered leaf matches remain.

    Returns {deleted, verified_gone, matched_name, pre_delete_rows,
    post_delete_rows, residue_in_list, reason?} — deleted=True ONLY on the full
    present→deleted→absent proof."""
    out: Dict[str, Any] = {"deleted": False, "verified_gone": False,
                           "form_id": form_id, "method": "browser-list-delete"}
    _router_push(session, _forms_list_route(location_id), expect_contains="form-builder")
    if not _wait_text_polling(session, "Create form"):
        out["reason"] = "the forms list did not render ('Create form' never appeared)"
        return out

    candidates = [c for c in dict.fromkeys([actual_title, form_name]) if c and c.strip()]
    out["candidates_checked"] = candidates
    found = ""
    pre = 0
    for cand in candidates:
        _fill(session, "Search for forms", cand, timeout=12)
        _wait_text_polling(session, cand, timeout_s=6)
        n = _eval_leaf_count(session, cand)
        if n > 0:
            found, pre = cand, n
            break
    if not found:
        out["reason"] = (
            f"no rendered list row positively matched any known name {candidates!r} "
            "(leaf-count 0/unknown for each) — NOT claiming deletion. If the build "
            "created a form under an unknown name it is RESIDUE; operator review "
            "required.")
        return out

    out["matched_name"] = found
    out["pre_delete_rows"] = pre
    if pre != 1:
        out["reason"] = (
            f"expected EXACTLY ONE rendered row title for {found!r} (title-leafs="
            f"{pre}) — several forms carry this exact name, so ANY Actions click "
            "could target the WRONG form. Fail-closed; operator review required.")
        return out

    # The per-row 'Actions' button is HOVER-REVEALED (live 2026-07-08: ONE
    # matched row but ZERO 'Actions' buttons in the DOM until the row is
    # hovered — the same reveal timing the v18.1.10 F4 fix killed for the
    # per-field remove control). Hover the matched row and POLL; a single
    # count-evaluation can never see a hover-revealed control.
    probe = _reveal_row_actions(session, found)
    out["pre_delete_actions_buttons"] = probe["visible"]
    out["actions_buttons_attached"] = probe["attached"]
    out["actions_hover_cycles"] = probe["hover_cycles"]
    if not probe["revealed"]:
        out["reason"] = (
            f"the row 'Actions' button for {found!r} never became VISIBLE within "
            f"{_ACTIONS_REVEAL_TIMEOUT_S:.0f}s (attached={probe['attached']}, "
            f"visible={probe['visible']}, {probe['hover_cycles']} hover cycle(s) "
            "with park-away re-entry) — the §3 per-row control is hover-revealed "
            "and did not reveal. Refusing to click blind; fail-closed; operator "
            "review required.")
        return out

    if probe["attached"] == 1:
        # Exactly ONE 'Actions' button in the whole DOM → the §3 locked
        # role+name anchor is unambiguous; use the actionability-checked
        # CLI click (hermetic probe 2026-07-08: single-attached role-exact
        # click lands on the correct row).
        out["actions_click_method"] = "role-exact"
        step_cp = _click_button(session, "Actions")
        if step_cp.returncode != 0:
            out["reason"] = f"row 'Actions' click did not land (rc={step_cp.returncode})"
            return out
    else:
        # SEVERAL rows carry an 'Actions' button (partial-name matches in the
        # filtered list). The role+name locator resolves the FIRST DOM match —
        # hermetic probe 2026-07-08: that can be a HIDDEN 0×0 button from the
        # WRONG row, and the CLI still returns rc=0 with NO click delivered.
        # So click the VISIBLE button NEAREST the matched row title (a per-row
        # control belongs to its row — ghl_iframe_drag._nearest_visible_match
        # doctrine) with a REAL pointer click at its measured center.
        out["actions_click_method"] = "nearest-coordinate"
        if probe["x"] < 0 or probe["y"] < 0:
            out["reason"] = (
                f"{probe['visible']} 'Actions' button(s) visible but the probe "
                "returned no nearest-to-row coordinates — refusing to click "
                "blind. Fail-closed; operator review required.")
            return out
        if not _mouse_click_at(session, probe["x"], probe["y"]):
            out["reason"] = ("row 'Actions' nearest-coordinate click did not land "
                             "(a mouse move/down/up command returned rc!=0)")
            return out
    if not _wait_text_polling(session, "Delete", timeout_s=8):
        out["reason"] = "the Actions menu never showed a 'Delete' item"
        return out
    step_cp = _click_menuitem(session, "Delete")
    if step_cp.returncode != 0:
        out["reason"] = f"'Delete' menuitem click did not land (rc={step_cp.returncode})"
        return out
    if not _wait_text_polling(session, "Delete form", timeout_s=8):
        out["reason"] = "the 'Delete form' confirm dialog never appeared"
        return out
    step_cp = _click_button(session, "Delete")
    if step_cp.returncode != 0:
        out["reason"] = f"confirm 'Delete' click did not land (rc={step_cp.returncode})"
        return out

    # POSITIVE post-verify: re-search and poll until ZERO rendered matches (the
    # present→absent transition is the proof; -1/unknown NEVER counts as gone).
    deadline = time.monotonic() + _TEXT_WAIT_TIMEOUT_S
    post = -1
    while True:
        _fill(session, "Search for forms", found, timeout=12)
        post = _eval_leaf_count(session, found)
        if post == 0 or time.monotonic() >= deadline:
            break
        time.sleep(1.0)
    out["post_delete_rows"] = post
    out["residue_in_list"] = (post != 0)
    if post == 0:
        out["deleted"] = True
        out["verified_gone"] = True
    else:
        out["reason"] = (
            f"post-delete leaf-count for {found!r} is {post} (expected 0) — the "
            "deletion did NOT verify; treating as residue. Operator review required.")
    return out


def _verify_no_residue(session: str, location_id: str, form_name: str,
                       possible_unnamed_orphan: bool) -> dict:
    """POSITIVE no-form-created verification (v18.1.5). When the walk captured no
    form id, cleanup must still PROVE the intended name is absent from the
    rendered Forms list — and, if a row IS found, actually delete it. A walk that
    stopped between the create-click and the id-capture may have created a form
    still carrying its DEFAULT name; that cannot be safely auto-deleted by name
    (any 'Form <n>' could be a real client form), so it is flagged loudly for the
    operator instead of being silently ignored."""
    out: Dict[str, Any] = {"method": "browser-list-no-residue-check",
                           "deleted": False, "verified_gone": False}
    _router_push(session, _forms_list_route(location_id), expect_contains="form-builder")
    if not _wait_text_polling(session, "Create form"):
        out["reason"] = "the forms list did not render — cannot verify no-residue"
        return out
    _fill(session, "Search for forms", form_name, timeout=12)
    n = _eval_leaf_count(session, form_name)
    out["intended_name_rows"] = n
    if n == 0:
        out["deleted"] = True
        out["verified_gone"] = True
        out["note"] = (f"no form id was captured AND the intended name {form_name!r} "
                       "is POSITIVELY absent from the rendered list (leaf-count 0)")
    elif n > 0:
        # A row with our intended name exists after all — delete it for real.
        out.update(_delete_form(session, location_id, "", form_name))
    else:
        out["reason"] = ("could not evaluate the rendered list (leaf-count unknown) — "
                         "NOT claiming clean")
    if possible_unnamed_orphan:
        out["possible_unnamed_orphan"] = True
        out["orphan_note"] = (
            "the walk stopped AFTER the create-confirm but BEFORE the id capture — "
            "a form still carrying its DEFAULT 'Form <n>' name may exist. A default-"
            "named form cannot be safely auto-deleted by name (it could be a real "
            "client form); OPERATOR REVIEW REQUIRED.")
    return out


# ── field placement (F5 Quick-Add + F6 Add-Object-Fields) — runtime snapshot-bind ──
# SELECTORS-LIVE-form.md §7 constraint: the builder is a cross-origin iframe; Quick-Add
# tiles + object-field rows carry NO stable CDP ref and top-frame CSS / `text=` cannot
# reach into the iframe. agent-browser 0.27.0 AUTO-INLINES the iframe and resolves the
# `drag` / `fill` / `click` verbs against the LIVE snapshot by VISIBLE TEXT — the exact
# primitive ghl_survey_builder.py._p2_pull_object_fields uses to place its object fields.
# So every step below is snapshot-and-bind by visible text (never an invented selector),
# and a genuine unplaceable field is a StopAndReport — NOT the default path.
#
# DROP-ANCHOR SPECS (v18.1.9 — the live 2026-07-08 `target-not-found` fix): each
# anchor is (visible-name, DOCUMENTED frame-scoped locator spec). Plain
# `text=Submit` is AMBIGUOUS inside the iframe — the Quick-Add panel carries a
# 'Submit' CATEGORY header + a 'Submit' tile (SELECTORS §8) alongside the canvas
# button, and attempt #5 proved the blind first-match binding times out against
# a hidden match. SELECTORS §5 locks the canvas landmark as role=button
# name='Submit' (conf 9); the default-field fallbacks use their §6 documented
# placeholder anchors (conf 8.5) — which can never collide with a panel tile's
# label text.
_CANVAS_DROP_ANCHORS: Tuple[Tuple[str, str], ...] = (
    ("Submit", "role=button:Submit"),                      # SELECTORS §5, conf 9
    ("Email", "placeholder=your@email.com"),               # SELECTORS §6, conf 8.5
    ("Phone", "placeholder=+1 (555) 000-0000"),            # SELECTORS §6, conf 8.5
    ("Last Name", "placeholder=Enter your last name"),     # SELECTORS §6, conf 8.5
    ("First Name", "placeholder=Enter your first name"),   # SELECTORS §6, conf 8.5
)


def _perform_smoke_first(session: str, *, iframe_selector: str = GHL_FORM_IFRAME_SELECTOR,
                         tile_text: str = "Email",
                         drop_spec: Optional[str] = None) -> dict:
    """Run ONE proof-drag (``ghl_iframe_drag.smoke_first`` — B-U16 item 3,
    generalized from the survey builder's ``_p2_smoke_test_drag``) BEFORE
    trusting the F5/F6 bulk Quick-Add/Object-Field drag run. Uses a
    UNIVERSAL, always-present Quick-Add tile (``'Email'`` — SELECTORS-LIVE-
    form.md's Personal Info category, present on every form) as the probe —
    NEVER one of the plan's own fields, so the probe can never collide with
    or duplicate a real placement — and undoes itself on success
    (``undo=True``) so the canvas is left exactly as it was. FAIL-CLOSED:
    raises StopAndReport BEFORE any bulk drag is attempted when the smoke
    probe does not verify — 'a CLI "✓ Done" that placed nothing is a FALSE
    PASS; the snapshot/store delta is the only honest arbiter' (shipped
    doctrine)."""
    if ghl_iframe_drag is None:
        raise StopAndReport(
            "smoke-first.dep",
            "the shared frame-scoped primitive (ghl_iframe_drag) is not "
            "importable — cannot run the one-proof-drag-before-a-bulk-run "
            "smoke test. STOP, do not brute-force a blind bulk run.")
    cdp_url = _get_cdp_url(session)
    if not cdp_url:
        raise StopAndReport(
            "smoke-first.cdp",
            "could not read the agent-browser session's CDP url (`get "
            "cdp-url`) to run the pre-bulk-run smoke probe. STOP.")
    spec = drop_spec or _canvas_drop_anchor(session)
    smoke = ghl_iframe_drag.smoke_first(  # type: ignore[union-attr]
        cdp_url,
        iframe_selector=iframe_selector,
        source=f"text={tile_text}",
        target=spec,
        verify_text=tile_text,
        url_marker="form-builder",
        undo=True,
    )
    if not smoke["ok"]:
        raise StopAndReport(
            "smoke-first",
            "the pre-bulk-run smoke probe (one proof-drag of "
            f"{tile_text!r} onto {spec!r}) did not verify — STOP before "
            f"attempting the real F5/F6 field drags. {smoke.get('error') or ''}")
    return smoke


def _canvas_drop_anchor(session: str, snap: str = "") -> str:
    """The frame-scoped locator SPEC of a landmark ON the form canvas to drop a
    dragged tile onto. A fresh scratch form always carries Submit + the default
    fields (CLICK-MAP Step 8 / §6), and the Submit button is a PERMANENT part of
    every form — so this always returns a spec: the first anchor whose visible
    name appears in the (ADVISORY) top-frame snapshot, else the documented
    role-scoped Submit spec. The snapshot is never the locate gate here — the
    AUTHORITATIVE, fail-closed resolve happens frame-scoped inside
    ``_perform_iframe_drag`` (`target-not-found`), the same doctrine as the
    tile locate (v18.1.5)."""
    snap = snap or _snapshot(session)
    for name, spec in _CANVAS_DROP_ANCHORS:
        if name in snap:
            return spec
    _log("drop-anchor: no anchor name in the (advisory) top-frame snapshot — "
         "falling back to the documented role-scoped Submit landmark; the "
         "frame-scoped resolve remains the authoritative gate")
    return _CANVAS_DROP_ANCHORS[0][1]


# ── F4 default-field reconciliation (v18.1.9) ────────────────────────────────
# GHL's Start-from-Scratch template PRE-SEEDS the canvas (SELECTORS §6 /
# DEFAULT_FORM_FIELDS); the plan splits those into default_fields_keep /
# default_fields_delete (see _build_form_plan), and the click list emits one F4
# delete_field step per unwanted default. Until v18.1.8 those steps were
# warn-and-KEEP — live 2026-07-08 attempt #5 shipped toward a form that would
# have carried BOTH the kept default 'Phone' and the plan's dragged 'Phone'
# (a duplicate-field spec violation), and the kept defaults are what made the
# canvas tall enough to push Submit below the fold. Deletion is now REAL and
# fail-closed, via the fields' DOCUMENTED canvas anchors — never invented CSS:
# placeholders per §6 (conf 8.5); the Terms & Conditions consent block has no
# placeholder, so its anchor is its consent paragraph text (§6 conf 6.5 —
# opening phrase confirmed in the live attempt-#5 builder screenshots).
_DEFAULT_FIELD_CANVAS_ANCHORS: Dict[str, str] = {
    "first name": "placeholder=Enter your first name",
    "last name": "placeholder=Enter your last name",
    "phone": "placeholder=+1 (555) 000-0000",
    "email": "placeholder=your@email.com",
    "terms & conditions": "text=I consent",
}


def _delete_default_field(session: str, name: str, evidence_root: str,
                          shot_n: List[int], warnings: List[str],
                          steps_done: List[str]) -> None:
    """F4 — reconcile ONE unwanted default field OFF the canvas (fail-closed).

    Proceeding past a failed delete is NOT an option: the form would ship with
    fields the plan excluded (client gets EXACTLY the spec), a kept default
    whose label equals a later Quick-Add tile poisons that drag's source text,
    and F5's count-delta placement proof would baseline against the leftover.
    An ALREADY-absent field is the desired end-state → recorded, not an error.

    v18.1.12: a remove failure now PERSISTS the primitive's rich diagnostics
    (strategy census, geometric candidate census with rejection reasons, aria
    snapshot, stimulation trace — see ghl_iframe_drag v1.3.0) as
    ``routing/f4-remove-diag-<field>.json`` AND captures a failure-moment
    screenshot, so a live miss produces decisive evidence (was the field even
    SELECTED? what WAS near its top-right?) instead of a generic timeout."""
    spec = _DEFAULT_FIELD_CANVAS_ANCHORS.get(name.strip().lower())
    if not spec:
        raise StopAndReport(
            f"F4.anchor:{name[:24]}",
            f"the plan asks to delete default field {name!r} but there is no "
            "DOCUMENTED canvas anchor for it (SELECTORS §6 / "
            "_DEFAULT_FIELD_CANVAS_ANCHORS). STOP — never invent a selector; "
            "capture the anchor live first.")
    try:
        rec = _perform_iframe_field_remove(session, spec)
    except StopAndReport as sr:
        details = getattr(sr, "details", None)
        diag_path = os.path.join(evidence_root, "routing",
                                 f"f4-remove-diag-{_slug(name)}.json")
        try:
            _write_json(diag_path, {"field": name, "anchor": spec,
                                    "step": sr.step, "reason": sr.reason,
                                    "details": details})
        except Exception as exc:  # noqa: BLE001 — evidence is best-effort
            _log(f"F4 diagnostics write best-effort failed for {diag_path!r}: {exc}")
            diag_path = ""
        # Failure-moment screenshot: shows whether the field was actually
        # SELECTED (blue outline + top-right pill) when the budget expired.
        _screenshot(session, _shot(evidence_root, shot_n,
                                   f"f4-delete-FAILED-{_slug(name)}"))
        wrapped = StopAndReport(
            f"F4.delete:{name[:24]}",
            f"could not remove default field {name!r} via its documented anchor "
            f"{spec!r} (underlying: {sr.step}). {sr.reason}"
            + (f" Diagnostics receipt: {diag_path}" if diag_path else ""))
        wrapped.details = details
        raise wrapped from sr
    if rec.get("already_absent"):
        steps_done.append(f"F4:default-absent:{name[:20]}")
        warnings.append(f"F4: default field {name!r} was already absent — "
                        "recorded as reconciled (idempotent no-op)")
        return
    steps_done.append(f"F4:delete:{name[:20]}")
    _screenshot(session, _shot(evidence_root, shot_n, f"f4-delete-{_slug(name)}"))


def _bind_field_props(session: str, field: dict, warnings: List[str]) -> None:
    """Bind the just-placed field's PROPERTY PANEL by VISIBLE LABEL (CLICK-MAP Steps
    16-18 / 36-37, SELECTORS §10). The field auto-selects on drop and its right-hand
    panel opens. Standard fields expose Label + Query Key + Field Width; a PRE-created
    custom field has only its Label editable (key/name locked, Step 35). Required and
    Hidden are mutually exclusive (already enforced in _resolve_fields). Each bind is
    best-effort snapshot-bound: a cosmetic miss is a WARNING — the field is already
    PLACED, the load-bearing outcome — never a hard stop, never a brute-forced selector."""
    label = field["label"]
    tag = label[:24]
    if _fill(session, "Label", label).returncode != 0:
        warnings.append(f"{tag!r}: Label property bind miss (in-iframe [runtime-capture]) — "
                        "field is placed; label left at its default")
    if field["source"] == "standard" and field.get("query_key"):
        _fill(session, "Query Key", field["query_key"])
    if int(field.get("width_pct", 100)) != 100:
        _fill(session, "Field Width", str(int(field["width_pct"])))
    if field.get("required"):
        _click_property_checkbox(session, "Required", warnings, tag)
    elif field.get("hidden"):
        _click_property_checkbox(session, "Hidden", warnings, tag)


def _ensure_quick_add_panel(session: str) -> str:
    """Ensure the left Form-Element ▸ Quick Add panel is open; return the live snapshot.
    A fresh scratch builder opens with it already visible (CLICK-MAP Step 9). If the
    'Quick Add' tab text is present, it is switched to via the frame-scoped primitive
    when available (B-U16 item 2 — real cross-origin reach for this TAB switch,
    replacing the prior top-frame-only best-effort attempt), falling back to the
    existing agent-browser click on a miss (never both — see
    _click_property_checkbox's same discipline). The '+' add-element toggle is
    icon-only [runtime-capture] and is deliberately NOT brute-forced."""
    snap = _snapshot(session)
    if "Quick Add" in snap:
        clicked_via_frame = False
        if ghl_iframe_drag is not None:
            try:
                _perform_frame_click(session, "text=Quick Add")
                clicked_via_frame = True
            except StopAndReport:
                pass  # fall through to the existing top-frame click
        if not clicked_via_frame:
            _click(session, "Quick Add")
        snap = _snapshot(session)
    return snap


# iframe-drag failure codes that mean "the TILE could not be located/revealed" —
# re-mapped to the honest F5.locate step (the live 2026-07-07 failure surface).
_DRAG_LOCATE_MISS_STEPS = (
    "iframe-drag:source-not-found",
    "iframe-drag:scroll-hint-not-found",
    "iframe-drag:source-scroll-failed",
)


def _place_quick_add_field(session: str, field: dict, evidence_root: str,
                           shot_n: List[int], warnings: List[str],
                           steps_done: List[str]) -> None:
    """F5 — place ONE standard field via Quick Add. LOCATE the tile INSIDE the
    builder iframe (frame-scoped, scrolling its CATEGORY into view when it sits
    below the panel fold — the live 2026-07-07 ``F5.locate:City`` fix, general for
    ANY field/category) → DRAG onto the canvas → VERIFY it landed → BIND props.
    StopAndReport ONLY on a genuine miss (tile absent even after the category
    scroll, no drop landmark, or nothing placed) — never as the default path.

    The top-frame a11y snapshot is ADVISORY here, never the locate gate: the
    Quick-Add panel scrolls, and a below-the-fold tile is legitimately absent from
    the snapshot while being 100%% reachable after a frame-scoped scroll (proven
    live 2026-07-07: ``City`` under ``Address``). The authoritative locate is the
    frame-scoped one inside ``_perform_iframe_drag`` — it has REAL access to the
    cross-origin frame and fails closed honestly."""
    tile = field["element"]
    label = field["label"]
    category = field.get("quick_add_category") or _find_quick_add_category(tile) or ""
    snap = _ensure_quick_add_panel(session)
    if tile not in snap:
        # Advisory only — the frame-scoped locate below is authoritative.
        _log(f"F5: tile {tile!r} not in the top-frame snapshot — relying on the "
             f"frame-scoped locate (category hint {category!r})")
    # The drop landmark is a frame-scoped locator SPEC (v18.1.9 — role-scoped
    # Submit per SELECTORS §5; the snapshot is only advisory for the choice,
    # the frame-scoped resolve inside the drag is the authoritative gate).
    drop_spec = _canvas_drop_anchor(session, snap)
    # FRAME-SCOPED drag (cross-origin iframe): agent-browser cannot reach the tile,
    # so hand THIS step to Playwright over the same session's CDP (verify=the field
    # label appears in the iframe). The category hint lets the primitive scroll the
    # tile's section into view first. Fail-closed inside _perform_iframe_drag; a
    # locate-class miss is re-raised as the honest F5.locate step.
    try:
        _perform_iframe_drag(session, tile, drop_spec, verify_text=label[:18],
                             source_scroll_hint=category)
    except StopAndReport as sr:
        if sr.step in _DRAG_LOCATE_MISS_STEPS:
            raise StopAndReport(
                f"F5.locate:{tile}",
                f"Quick-Add tile {tile!r} could not be located inside the builder "
                f"iframe even after scrolling its category {category or '?'!r} into "
                f"view (frame-scoped locate; underlying: {sr.step}). {sr.reason}") from sr
        raise
    # The AUTHORITATIVE placement gate already ran INSIDE the iframe: the
    # frame-scoped drag verifies `verify_text` with real frame access and raises
    # `not-placed` (→ StopAndReport) when the field did not land. The top-frame
    # snapshot below is secondary EVIDENCE only — the auto-inlined snapshot can
    # legitimately lag/miss in-iframe content (the same unreliable surface that
    # produced the false F5.locate:City STOP), so it must never hard-fail a
    # placement the frame itself verified.
    _wait_text(session, label[:18], timeout=15)
    after = _snapshot(session)
    if label[:12] not in after and tile not in after:
        warnings.append(
            f"F5: {label!r} placed + verified IN-FRAME, but the top-frame snapshot "
            "does not (yet) echo it — snapshot lag recorded as evidence, not a STOP")
    _bind_field_props(session, field, warnings)
    steps_done.append(f"F5:place:{label[:24]}")
    _screenshot(session, _shot(evidence_root, shot_n, f"f5-{_slug(label)}"))


def _place_object_field(session: str, field: dict, evidence_root: str,
                        shot_n: List[int], warnings: List[str],
                        steps_done: List[str]) -> None:
    """F6 — place ONE PRE-CREATED (Skill 44) custom field via Add Object Fields.
    Switch tab → Search by Name → DRAG by visible label → VERIFY → BIND Label only.
    The field is NEVER minted on the fly; if it is absent that means Skill 44 has not
    created it yet → StopAndReport (fail-closed, CLICK-MAP Phase H / §7)."""
    label = field["label"]
    key = field.get("field_key", "")
    _click(session, "Add Object Fields")
    _wait_text(session, "Search by Name", timeout=15)
    _fill(session, "Search by Name", label[:24])
    snap = _snapshot(session)
    if label[:12] not in snap and not (key and key in snap):
        _fill(session, "Search by Name", key)          # retry by the zhc_ key
        snap = _snapshot(session)
    if label[:12] not in snap and not (key and key in snap):
        raise StopAndReport(
            f"F6.locate:{key or label}",
            f"pre-created custom field {label!r} ({key!r}) is not listed under Add Object "
            "Fields after Search-by-Name. It must be created FIRST by Skill 44 (caf, "
            "LOCATION PIT) — the browser never mints a custom field on the fly (CLICK-MAP "
            "Phase H / SELECTORS §7). STOP — do not brute-force.")
    drop_spec = _canvas_drop_anchor(session, snap)   # frame-scoped SPEC (v18.1.9)
    # FRAME-SCOPED drag (cross-origin iframe) — same fix as F5; the pre-created
    # object-field row is a non-interactive node agent-browser cannot reach.
    # (No scroll hint needed: Search-by-Name just filtered the list to this row,
    # and drive_drag scrolls the row into view itself when it sits below a fold.)
    _perform_iframe_drag(session, label[:24], drop_spec, verify_text=label[:18])
    # Authoritative placement gate = the frame-scoped verify above (raises
    # `not-placed` on a miss). Top-frame snapshot = secondary evidence only —
    # same doctrine as F5 (the auto-inlined snapshot can lag in-iframe content).
    _wait_text(session, label[:18], timeout=15)
    if label[:12] not in _snapshot(session):
        warnings.append(
            f"F6: {label!r} placed + verified IN-FRAME, but the top-frame snapshot "
            "does not (yet) echo it — snapshot lag recorded as evidence, not a STOP")
    _bind_field_props(session, field, warnings)
    _fill(session, "Search by Name", "")               # clear for the next field
    steps_done.append(f"F6:place:{label[:24]}")
    _screenshot(session, _shot(evidence_root, shot_n, f"f6-{_slug(label)}"))


# ── the click-list walk (locked-anchor interpreter) ──────────────────────────
def _walk_click_list(session: str, click_list: dict, plan: dict, evidence_root: str,
                     shot_n: List[int], warnings: List[str], steps_done: List[str],
                     walk_state: Optional[Dict[str, Any]] = None,
                     state: Optional["ghl_run_state.RunState"] = None,
                     stop_after: str = "") -> dict:
    """Interpret each click-list step through the LOCKED anchors. Returns
    {form_id, form_url, embed_snippet, actual_title}. Raises StopAndReport on a
    REQUIRED miss.

    ``walk_state`` (v18.1.5): a caller-owned MUTABLE dict that receives
    ``form_id`` / ``actual_title`` THE MOMENT they are captured. The old
    return-value-only contract THREW THE CAPTURED ID AWAY whenever a LATER step
    raised StopAndReport — live 2026-07-07: the walk had created a real form and
    captured its id at F2, then STOPped at F5, and cleanup (seeing only the
    never-assigned local) claimed 'no form was created — nothing to delete'
    while the form sat live in the account. State that cleanup depends on must
    survive the exception path."""
    st: Dict[str, Any] = walk_state if walk_state is not None else {}
    loc = plan["location_id"]
    form_name = plan["form_name"]
    form_id = ""
    form_url = ""
    embed = ""
    f5_done = [False]   # place ALL standard fields on the first F5 step, then skip
    f6_done = [False]   # place ALL pre-created custom fields on the first F6 step
    smoke_done = [False]   # ONE proof-drag before trusting the F5/F6 bulk run (B-U16 item 3)
    keep_defaults = set(plan.get("default_fields_keep", []))

    # F5 uniform keepalive + pre-phase re-mint (SKILL-6-BULLETPROOF-SPEC-v1 F5):
    # the survey builder already threads this through every Part-2 phase; the
    # form builder's click-list walk had the import but never wired it in (a
    # confirmed gap — see build ledger). Fire the check once per PHASE
    # TRANSITION (F1→F2→...→F13), not per click-list step, so a long form build
    # never crosses the ~60min id_token window uncovered.
    _keepalive = _RealKeepalive() if _RealKeepalive is not None else None
    _last_phase: List[Optional[str]] = [None]

    # ── U8: resume ──────────────────────────────────────────────────────────────
    # A phase is skipped WHOLESALE (all of its click-list steps), never half-walked
    # — a phase is the unit the ledger commits, so it is also the unit resume trusts.
    skip_phases: set = set()
    if state is not None:
        skip_phases = {s.name for s in FORM_PHASES if state.should_skip(s.name)}
        carried_id = state.carry_get("form_id") or ""
        if "F2" in skip_phases and carried_id:
            # The form already EXISTS. Re-walking F2 would create a SECOND one — the
            # exact duplicate-object bug a naive "just start over" resume produces.
            # Route straight into the existing form's builder instead.
            form_id = carried_id
            form_url = state.carry_get("form_url") or ""
            embed = state.carry_get("embed_snippet") or ""
            st["form_id"] = form_id
            st["actual_title"] = state.carry_get("actual_title") or ""
            _log(f"resume: form {form_id!r} already created — routing straight to its "
                 f"builder (F2 create SKIPPED, no duplicate form)")
            _router_push(session, _form_builder_route(loc, form_id),
                         expect_contains="form-builder")
            _screenshot(session, _shot(evidence_root, shot_n, "resume-reentered-form"))
        elif "F2" in skip_phases and not carried_id:
            # Ledger says the form was created but no id survived: resuming would
            # build a duplicate. Fail closed rather than guess.
            raise StopAndReport(
                "F2",
                "run state says the form was created but carries no form_id — refusing "
                "to resume, because re-walking F2 would create a DUPLICATE form. "
                "Start a fresh run (drop --resume) after deleting any orphan.",
            )

    def _commit_phase(name: Optional[str]) -> None:
        """Commit a phase to the ledger the moment it is fully walked (not at the end
        of the run) — a process killed at F7 must find F1…F6 already durable."""
        if state is None or not name or name in skip_phases:
            return
        state.mark_done(name, {"steps": len([s for s in steps_done
                                             if s.startswith(f"{name}:")])})
        if name == "F2" and form_id:
            state.carry_set("form_id", form_id)
            state.carry_set("actual_title", st.get("actual_title", ""))
        if name == "F10":
            if form_url:
                state.carry_set("form_url", form_url)
            if embed:
                state.carry_set("embed_snippet", embed)

    for step in click_list["steps"]:
        phase, action, target = step["phase"], step["action"], (step["target"] or "")
        tgt = target.strip()
        tag = f"{phase}:{action}:{tgt[:36]}"

        if phase != _last_phase[0]:
            # Phase transition: the phase we are LEAVING is now complete.
            _commit_phase(_last_phase[0])
            if stop_after and _last_phase[0] == stop_after:
                raise ghl_run_state.StopAfterPhase(stop_after)
            if state is not None and phase in skip_phases:
                _log(f"PHASE {phase}: SKIP — already completed in run {state.run_id}")
                state.mark_skipped(phase)
                _last_phase[0] = phase
                continue
            _pre_phase_check(session, _keepalive)
            if state is not None:
                state.mark_running(phase)
            _last_phase[0] = phase

        if phase in skip_phases:
            continue

        # F1 — navigate to the Forms list (collapse nav+Sites+Forms → one router.push;
        # 'Sites' left-rail is conf 5 / unreliable, so we never click it).
        if phase == "F1":
            if action == "click" and tgt.lower() == "forms":
                _router_push(session, _forms_list_route(loc), expect_contains="form-builder")
                _wait_text(session, "Create form", timeout=25)
                _screenshot(session, _shot(evidence_root, shot_n, "f1-forms-list"))
                steps_done.append(tag)
            continue

        # F2 — create the form
        if phase == "F2":
            if action == "click" and tgt.lower().startswith("create form"):
                # The modal-open wait rc is CHECKED (one retry): live 2026-07-07 the
                # modal never opened on a slow, form-heavy account, the ignored rc let
                # the walk blunder into Create/capture blind, and the miss surfaced two
                # steps later as a misleading F2.create "iframe src" failure (evidence:
                # f2-create-modal shot byte-identical to the forms-list shot).
                #
                # The wait itself POLLS on a deadline (live 2026-07-07 follow-up, same
                # doctrine as _capture_form_id's poll-with-deadline fix): a single
                # _wait_text call does not actually get the timeout=20 budget from
                # agent-browser — see _wait_text_polling's module notes.
                _click(session, "Create form")
                modal_ok = _wait_text_polling(session, "Start from Scratch")
                if not modal_ok:
                    _log("F2: create-modal wait missed — retrying the 'Create form' click once")
                    _click(session, "Create form")
                    modal_ok = _wait_text_polling(session, "Start from Scratch")
                if not modal_ok:
                    raise StopAndReport(
                        "F2.modal",
                        "clicked 'Create form' (twice) but the Create-new-form modal never "
                        "showed 'Start from Scratch' — STOP here honestly instead of "
                        f"blundering into the Create/capture steps blind ({_capture_entry_diag(session)})")
                _screenshot(session, _shot(evidence_root, shot_n, "f2-create-modal"))
                steps_done.append(tag)
            elif action == "confirm":
                steps_done.append(tag)                      # Scratch is the default radio
            elif action == "click" and tgt == "Create":
                # Modal-CONFIRM click — MUST be role=button + EXACT accessible
                # name, never a 'Create' substring click (live 2026-07-07, the
                # defect UNDER the v18.1.1–v18.1.3 fixes, all of which remain
                # in place): at this instant THREE on-screen elements contain
                # 'Create' — the header '+ Create form' button behind the
                # overlay, the modal title 'Create new form', and the blue
                # confirm button. The old `find text Create click` emission
                # (the _click substring helper) resolved rc=0 against the
                # FIRST DOM-order match (the header button), the SPA never
                # left /form-builder/main, and the id-capture poll below
                # timed out honestly. See _click_button's probe evidence.
                confirm = _click_button(session, "Create")
                if confirm.returncode != 0:
                    # With the modal PROVEN open (gated on 'Start from Scratch'
                    # above) an exact-name miss is structural, not timing —
                    # STOP here honestly instead of polling the id capture for
                    # a navigation that can never happen.
                    raise StopAndReport(
                        "F2.confirm",
                        "the Create-new-form modal is open but no button with "
                        "accessible name EXACTLY 'Create' was found/clickable "
                        f"(rc={confirm.returncode}) — the confirm click did NOT "
                        f"land ({_capture_entry_diag(session)})")
                entered = _wait_text(session, "Save", timeout=30)
                # _capture_form_id POLLS (deadline-bounded) — the builder iframe mounts
                # asynchronously after the SPA route flips, so a single-shot read here
                # raced it (live 2026-07-07). The Save-wait rc is evidence, not a gate:
                # the capture poll is the authoritative entered-the-builder check.
                form_id = _capture_form_id(session)
                if not form_id:
                    st["stopped_after_create_confirm"] = True   # a DEFAULT-named form may exist
                    raise StopAndReport(
                        "F2.create",
                        "entered the builder but could not read the form id from the "
                        "/form-builder-v2/<id> route after polling "
                        f"{_FORM_ID_CAPTURE_TIMEOUT_S:.0f}s (Save-wait rc={entered.returncode}; "
                        f"page-state {_capture_entry_diag(session)})")
                st["form_id"] = form_id     # survives a later-step StopAndReport (v18.1.5)
                _screenshot(session, _shot(evidence_root, shot_n, "f2-builder"))
                steps_done.append(tag)
            elif action == "click" and tgt.lower() == "use a template":
                warnings.append("F2: template path requested — minimal live run uses Start-from-Scratch")
            continue

        # F3 — rename via the FRAME-SCOPED inline-title primitive (v18.1.5).
        # Runs BEFORE any field dragging (the click list orders F3 ahead of F5/F6)
        # so a created form is NEVER left carrying its default name past this
        # point. FAIL-CLOSED by default (plan['rename_required']): an unrenamed
        # container is exactly the orphan hazard that bit the live 2026-07-07 run
        # — and even on STOP, the receipt's actual_title lets cleanup positively
        # target the form by the name it REALLY carries.
        if phase == "F3":
            if tag.startswith("F3:click") or action == "click":
                r = _rename_form_title(session, form_name)
                st["actual_title"] = r.get("actual_title", "")
                st["rename"] = r
                if r["renamed"]:
                    steps_done.append(f"F3:rename:{form_name[:24]}")
                    _screenshot(session, _shot(evidence_root, shot_n, "f3-renamed"))
                elif plan.get("rename_required", True):
                    _screenshot(session, _shot(evidence_root, shot_n, "f3-rename-failed"))
                    raise StopAndReport(
                        "F3.rename",
                        f"could not rename the form to {form_name!r} via the frame-"
                        f"scoped inline-title primitive ({r['reason']}). The form "
                        f"currently carries {r['actual_title'] or 'an unknown name'!r} "
                        "(recorded for cleanup targeting). STOP — a build must never "
                        "proceed on an unlabeled container (rename_required=True).")
                else:
                    warnings.append(
                        f"F3: rename to {form_name!r} failed ({r['reason']}) and "
                        "rename_required=False — proceeding; cleanup will target the "
                        f"read-back title {r['actual_title']!r}")
            continue

        # F4 — default-field reconciliation (v18.1.9): DELETE each unwanted
        # default FOR REAL via the frame-scoped seam (select the field by its
        # documented §6 anchor → role=link 'Remove field' → count-decrease
        # proof). The old warn-and-keep stub left 'Phone' + 'Terms & Conditions'
        # on the canvas (live 2026-07-08 attempt #5) — a spec violation that
        # also poisoned the F5 drag surfaces. Fail-closed inside
        # _delete_default_field; already-absent = truthful idempotent no-op.
        if phase == "F4":
            if action == "delete_field" and tgt:
                _delete_default_field(session, tgt, evidence_root, shot_n,
                                      warnings, steps_done)
            continue

        # F5 / F6 — field placement. On the FIRST step of each phase we place ALL of
        # that phase's fields via runtime snapshot-and-bind (locate → drag → verify →
        # bind), then skip the phase's now-redundant per-property sub-steps. A field
        # already present as a KEPT DEFAULT is not re-dragged (no duplicates). A genuine
        # unplaceable field STOPs-and-reports — never the default path, never invented CSS.
        if phase == "F5":
            if not smoke_done[0]:
                # B-U16 item 3: ONE proof-drag before trusting the bulk F5/F6
                # run — "a CLI '✓ Done' that placed nothing is a FALSE PASS"
                # (shipped doctrine). A failed smoke aborts HERE, before any
                # of the plan's real fields are touched.
                _perform_smoke_first(session)
                smoke_done[0] = True
            if not f5_done[0]:
                for f in plan["fields"]:
                    if f["source"] != "standard":
                        continue
                    if f["label"] in keep_defaults or f["element"] in keep_defaults:
                        steps_done.append(f"F5:default-kept:{f['label'][:20]}")
                        continue
                    _place_quick_add_field(session, f, evidence_root, shot_n, warnings, steps_done)
                f5_done[0] = True
            continue
        if phase == "F6":
            if not f6_done[0]:
                for f in plan["fields"]:
                    if f["source"] != "custom":
                        continue
                    _place_object_field(session, f, evidence_root, shot_n, warnings, steps_done)
                f6_done[0] = True
            continue

        # F7 — save (draft)
        if phase == "F7" and action == "click":
            _click(session, "Save")
            _wait_text(session, "Saved", timeout=20)
            _screenshot(session, _shot(evidence_root, shot_n, "f7-saved"))
            steps_done.append(tag)
            continue

        # F8 — styles / custom CSS (icon-toolbar SVG + in-iframe panels = runtime-capture)
        if phase == "F8":
            if plan.get("styling", {}).get("custom_css") or plan.get("styling", {}).get("themes"):
                warnings.append(f"F8: styles surface {tgt[:24]!r} is icon-toolbar/in-iframe "
                                "runtime-capture — skipped in the minimal run (no brute-force)")
            continue

        # F9 — preview
        if phase == "F9" and action == "click":
            _click(session, "Preview")
            _screenshot(session, _shot(evidence_root, shot_n, "f9-preview"))
            steps_done.append(tag)
            continue

        # F10 — Integrate + capture the embed snippet + the form link
        if phase == "F10":
            if action == "click" and tgt.lower() == "integrate":
                _click(session, "Integrate")
                _wait_text(session, "Copy embed code", timeout=20)
                _screenshot(session, _shot(evidence_root, shot_n, "f10-integrate"))
                embed = _capture_embed(session)
                if not embed:
                    raise StopAndReport("F10.embed",
                                        "Integrate modal is open but no embed snippet was found in a "
                                        "textarea/code element (snapshot-and-bind miss)")
                form_url = _capture_form_link(session)
                _write_json(os.path.join(evidence_root, "routing", "embed-snippet.json"),
                            {"embed_snippet": embed, "form_link": form_url, "captured_at": _ts()})
                steps_done.append(tag)
            continue

        # F11 — embed → page splice: a ghl_rest_canvas handoff (VERBATIM snippet, no SRI).
        if phase == "F11":
            tgt_spec = plan.get("embed", {}).get("target", {})
            _write_json(os.path.join(evidence_root, "routing", "embed-handoff.json"), {
                "owner": "ghl_rest_canvas",
                "embed_snippet": embed,
                "paste": "VERBATIM into a Custom Code element; NO SRI attrs",
                "wrap_marker": f"zhc_form_{_slug(form_name)}",
                "target": tgt_spec,
                "then": "ghl_verify.render_check (HTTP 200 + zhc_ marker in RENDERED DOM)",
            })
            warnings.append("F11: embed→page splice recorded as a ghl_rest_canvas handoff "
                            "(routing/embed-handoff.json)")
            continue

        # F12 — tag attachment: a Skill-44 'Form Submitted → Add Contact Tag' workflow handoff.
        if phase == "F12":
            warnings.append("F12: tag attachment is a Skill-44 workflow handoff (zhc_ tags pre-created)")
            continue

        # F13 — verify is performed by the caller (render_check).
        if phase == "F13":
            steps_done.append(tag)
            continue

    # The LAST phase gets no transition to commit it — commit it here.
    _commit_phase(_last_phase[0])

    return {"form_id": form_id, "form_url": form_url, "embed_snippet": embed,
            "actual_title": st.get("actual_title", "")}


def _live_build(task: dict, plan: dict, click_list: dict, fields: List[dict],
                dep_plan: dict, preflight: dict, evidence_root: str, started: float,
                state: Optional["ghl_run_state.RunState"] = None) -> dict:
    """Drive the live browser build end-to-end: seed → land → walk → capture embed →
    write build receipt → verify → CLEANUP (delete form + close session). Every
    failure is a STOP-and-report; the created form is ALWAYS deleted in finally.

    RESUME + CLEANUP, and why they do not fight (U8): cleanup deletes the form on
    every path that REACHES it, so a run that ends normally leaves nothing to
    resume — and nothing that needs resuming. Resume exists for the runs that never
    reach cleanup at all: SIGKILL, a dead box, a browser crash. Those leave a real
    form behind, and `--resume <run_id>` re-enters THAT form instead of building a
    second one. A ``--stop-after-phase`` stop deliberately skips cleanup for the
    same reason: the half-built form must survive for the resume to find it.
    """
    location_id = plan["location_id"]
    os.environ["GHL_LOCATION_ID"] = location_id      # canonical session-name consistency
    session = _canonical_session(location_id)
    shot_n: List[int] = [0]
    warnings: List[str] = []
    steps_done: List[str] = []
    built: Dict[str, Any] = {}
    cleanup: Dict[str, Any] = {"attempted": False}
    form_id = ""
    stop: Optional[StopAndReport] = None
    stopped_after: str = ""
    stop_after: str = str(task.get("stop_after_phase", "") or "")
    # Mutable walk state (v18.1.5): form_id / actual_title recorded AT CAPTURE
    # TIME so cleanup still sees them when a LATER step raises StopAndReport —
    # the old locals-only flow claimed 'no form was created' after a mid-walk
    # STOP even though a real, id-captured form existed (live 2026-07-07).
    walk_state: Dict[str, Any] = {}

    # D6 headless + agent-browser version-pin guards (refuse a headed window / drift).
    browser_manager.headless_guard()                 # type: ignore[union-attr]
    browser_manager.assert_agent_browser_version()   # type: ignore[union-attr]

    # ONE canonical browser_session brackets every emitter (ghl_builder.browser_cmd
    # REFUSES to run outside it). Enter it manually so the drive/cleanup body keeps
    # its indentation; _close_session() does the real close of the seeded session.
    _session_cm = browser_manager.browser_session(location_id)   # type: ignore[union-attr]
    _sess = _session_cm.__enter__()
    if _sess:
        session = _sess

    try:
        auth = _seed_and_land(session, location_id, evidence_root)
        _write_json(os.path.join(evidence_root, "routing", "auth-receipt.json"),
                    {"landed": auth["landed"], "seeded_at": _ts()})
        _screenshot(session, _shot(evidence_root, shot_n, "auth-landed"))

        walk = _walk_click_list(session, click_list, plan, evidence_root,
                                shot_n, warnings, steps_done, walk_state,
                                state=state, stop_after=stop_after)
        form_id = walk["form_id"]
        form_url = walk["form_url"]
        embed = walk["embed_snippet"]

        # Build receipt for the render gate (qc-built-form.sh). A `verify` block is
        # populated ONLY when a zhc_-marked RENDERED surface exists (embed spliced
        # into a page with a zhc_ wrapper, or a zhc_ custom field). A bare scratch
        # form has no zhc_ rendered token, so verify is DEFERRED (honest — the gate
        # reports inconclusive rather than fabricating a pass).
        verify_block: Dict[str, Any] = {}
        zhc_custom = [f for f in fields if f.get("source") == "custom"]
        if form_url and zhc_custom:
            verify_block = {"preview_url": form_url,
                            "marker": zhc_custom[0]["field_key"],
                            "page_id": form_id}
        built = {
            "form_id": form_id, "form_name": plan["form_name"], "form_url": form_url,
            "builder_url": f"https://{GHL_FORM_BUILDER_HOST}/form-builder-v2/{form_id}",
            "embed_snippet": embed, "verify": verify_block,
            "warnings": warnings, "steps_done": steps_done, "built_at": _ts(),
        }
        _write_json(os.path.join(evidence_root, "routing", "form-built.json"), built)

        # F13 verify (only when a zhc_ rendered surface exists; else deferred).
        verify_result: Dict[str, Any] = {"status": "deferred",
                                         "reason": "no zhc_ rendered surface yet (embed not spliced "
                                                   "into a page / no zhc_ custom field) — run "
                                                   "qc-built-form.sh after the F11 splice"}
        if verify_block and _ghl_verify_available():
            import ghl_verify  # type: ignore
            rec = ghl_verify.verify_page(   # already inside the active browser_session
                {"step": "form", "name": plan["form_name"], "page_id": form_id,
                 "preview_url": verify_block["preview_url"], "marker": verify_block["marker"]},
                run_dir=evidence_root, live=True)
            verify_result = {"status": "ran", "PASS": bool(rec.get("PASS")),
                             "http": rec.get("http"),
                             "marker_in_rendered_dom": rec.get("marker_in_rendered_dom"),
                             "render_errors": rec.get("render_errors", [])}

    except ghl_run_state.StopAfterPhase as sap:
        # An OPERATOR-requested stop, not a failure. Cleanup is deliberately SKIPPED:
        # deleting the half-built form here would delete the very thing --resume is
        # meant to pick back up.
        stopped_after = sap.phase
        _log(f"STOPPED after phase {sap.phase!r} (--stop-after-phase) — form left in "
             f"place for --resume; state committed.")
    except StopAndReport as sr:
        stop = sr
        _log(f"STOP-and-report @ {sr.step}: {sr.reason}")
    except Exception as exc:  # noqa: BLE001
        stop = StopAndReport("unexpected", f"{type(exc).__name__}: {exc}")
        _log(f"live build unexpected error: {type(exc).__name__}: {exc}")
    finally:
        # CLEANUP — ALWAYS delete the created form, then close the session (no
        # residue), with a POSITIVE verification either way (v18.1.5): the id +
        # actual title come from walk_state so a mid-walk STOP can no longer hide
        # a created form, and 'nothing to delete' is only ever CLAIMED after the
        # rendered Forms list positively shows zero rows for the intended name.
        #
        # ONE exception (U8): a --stop-after-phase stop leaves the form ALIVE on
        # purpose. Deleting it would destroy the object the operator explicitly
        # stopped in order to inspect, and would leave --resume nothing to resume.
        if stopped_after:
            cleanup.update({
                "attempted": False, "deleted": False, "verified_gone": False,
                "skipped_reason": (f"--stop-after-phase {stopped_after}: form intentionally "
                                   f"LEFT IN PLACE so --resume can re-enter it"),
                "form_id": walk_state.get("form_id") or form_id,
            })
        else:
            cleanup["attempted"] = True
            try:
                effective_form_id = walk_state.get("form_id") or form_id
                actual_title = walk_state.get("actual_title", "")
                if effective_form_id:
                    cleanup.update(_delete_form(session, location_id, effective_form_id,
                                                plan["form_name"], actual_title=actual_title))
                    _screenshot(session, _shot(evidence_root, shot_n, "cleanup-deleted"))
                else:
                    cleanup.update(_verify_no_residue(
                        session, location_id, plan["form_name"],
                        possible_unnamed_orphan=bool(
                            walk_state.get("stopped_after_create_confirm"))))
                    _screenshot(session, _shot(evidence_root, shot_n, "cleanup-no-residue"))
            except Exception as exc:  # noqa: BLE001
                cleanup["deleted"] = False
                cleanup["verified_gone"] = False
                cleanup["error"] = f"{type(exc).__name__}: {exc}"
                warnings.append(f"cleanup: delete/verify raised: {exc}")

        try:
            _session_cm.__exit__(None, None, None)   # emit the teardown step
        except Exception:  # noqa: BLE001
            pass
        _close_session(location_id)                  # REAL close of the seeded session
        _write_json(os.path.join(evidence_root, "routing", "cleanup.json"), cleanup)

    if stopped_after:
        return {
            "pages": [], "location_gate_ok": bool(location_id),
            "duration_s": time.monotonic() - started,
            "form_url": "", "form_id": walk_state.get("form_id") or form_id,
            "embed_code": "", "stopped_after_phase": stopped_after,
            "run_id": state.run_id if state is not None else "",
            "warnings": warnings, "steps_done": steps_done,
            "cleanup": cleanup, "preflight": preflight,
        }

    duration = time.monotonic() - started
    if stop is not None:
        return {
            "pages": [], "location_gate_ok": False, "duration_s": duration,
            "form_url": "", "form_id": walk_state.get("form_id") or form_id,
            "actual_title": walk_state.get("actual_title", ""), "embed_code": "",
            "error": str(stop), "stop_step": stop.step, "stop_reason": stop.reason,
            "warnings": warnings, "steps_done": steps_done, "cleanup": cleanup,
            "preflight": preflight,
        }
    return {
        "pages": built.get("form_url") and [{"step": "form", "form_id": form_id,
                                             "form_url": built.get("form_url")}] or [],
        "location_gate_ok": bool(location_id),
        "duration_s": duration,
        "form_url": built.get("form_url", ""), "form_id": form_id,
        "embed_code": built.get("embed_snippet", ""),
        "verify": verify_result, "warnings": warnings, "steps_done": steps_done,
        "cleanup": cleanup, "preflight": preflight, "dry_run": False,
    }


def _ghl_verify_available() -> bool:
    try:
        import ghl_verify  # noqa: F401  # type: ignore
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def build_form(task: dict, evidence_root: str, *, dry_run: bool = True,
               state: Optional["ghl_run_state.RunState"] = None) -> dict:
    """Build a GHL (Convert and Flow) FORM via browser-control.

    THINK layer always runs (preflight + plan + dependency plan + field map +
    click list). LIVE browser execution runs only when dry_run=False AND the
    real skill modules (ghl_builder / browser_manager) are importable.

    ``state`` (U8): a RunState turns the click-list walk's own F1…F13 phases into
    resume points. ``None`` (the dispatcher / library callers) = no checkpointing,
    and the walk behaves exactly as it always did.
    """
    started = time.monotonic()
    dry_run = bool(task.get("dry_run", dry_run))
    os.makedirs(os.path.join(evidence_root, "routing"), exist_ok=True)
    os.makedirs(os.path.join(evidence_root, "shots"), exist_ok=True)

    fields = _resolve_fields(task)
    dep_plan = plan_dependencies(
        fields, task,
        existing_field_keys=task.get("existing_field_keys"),
        existing_tags=task.get("existing_tags"),
    )
    preflight = _run_preflight(task, fields, dep_plan, live=not dry_run)

    plan = _build_form_plan(task, fields, dep_plan)
    plan_path = os.path.join(evidence_root, "routing", "form-plan.json")
    dep_path = os.path.join(evidence_root, "routing", "form-dependency-plan.json")
    click_path = os.path.join(evidence_root, "routing", "form-click-list.json")
    _write_json(plan_path, plan)
    _write_json(dep_path, dep_plan)

    if not preflight["pass"]:
        _write_json(os.path.join(evidence_root, "routing", "form-preflight.json"), preflight)
        return {"pages": [], "location_gate_ok": False,
                "duration_s": time.monotonic() - started, "form_url": "", "embed_code": "",
                "preflight": preflight, "plan_path": plan_path, "error": preflight.get("stop_reason")}

    click_list = _emit_click_list(task, fields, plan)
    _write_json(click_path, click_list)
    _write_json(os.path.join(evidence_root, "routing", "form-preflight.json"), preflight)

    if dry_run:
        _log(f"[dry-run] plan + dependency-plan + click list ({click_list['total_steps']} steps) written.")
        return {
            "pages": plan["fields"], "location_gate_ok": bool(plan["location_id"]),
            "duration_s": time.monotonic() - started, "form_url": "", "embed_code": "",
            "preflight": preflight, "dependency_plan": dep_plan,
            "plan_path": plan_path, "dependency_plan_path": dep_path,
            "click_list_path": click_path, "click_list": click_list, "dry_run": True,
        }

    # ── LIVE browser execution — the DUMB / DO layer walks the click list ────────
    if ghl_builder is None or browser_manager is None:
        raise RuntimeError(
            "LIVE build requires the Skill-6 tools/ modules ghl_builder + browser_manager "
            "importable on sys.path (this module ships IN 06-ghl-install-pages/tools/). "
            "They are absent in this environment, so the live browser path cannot run — "
            "run --dry-run/--selftest here, and run live from the skill's tools/ dir only "
            "after Skill 44 has created the dependency plan's custom fields + tags."
        )
    # Walks click_list['steps'] via agent-browser (router.push / click / wait / fill /
    # type / eval / snapshot / screenshot): seeds auth token-only (never reloads),
    # captures the embed snippet at F10, records F11/F12 handoffs to ghl_rest_canvas /
    # Skill 44, verifies via ghl_verify.render_check, and ALWAYS deletes the built form
    # in cleanup. In-iframe surfaces are snapshot-and-bound at runtime; a REQUIRED miss
    # is a STOP-and-report (no invented CSS, no brute-force).
    return _live_build(task, plan, click_list, fields, dep_plan, preflight,
                       evidence_root, started, state=state)


# ---------------------------------------------------------------------------
# Self-test — no network, no browser, no skill deps
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    errors: List[str] = []

    # 1. zhc helpers are idempotent + correctly shaped
    if zhc_field_key("Podcast Rating") != "zhc_podcast_rating":
        errors.append(f"zhc_field_key wrong: {zhc_field_key('Podcast Rating')!r}")
    if zhc_field_key("zhc_podcast_rating") != "zhc_podcast_rating":
        errors.append("zhc_field_key double-prefixed")
    if zhc_tag("Podcast Lead!!") != "zhc_podcast_lead":
        errors.append(f"zhc_tag wrong: {zhc_tag('Podcast Lead!!')!r}")
    if ensure_zhc_name("Signup Form") != "ZHC Signup Form":
        errors.append(f"ensure_zhc_name wrong: {ensure_zhc_name('Signup Form')!r}")
    if ensure_zhc_name("zhc already") != "zhc already":
        errors.append("ensure_zhc_name double-prefixed")

    # 2. idempotency: a field whose key already exists → action=reuse
    fields = _resolve_fields({"form_fields": _reference_fields()})
    dep = plan_dependencies(fields, {"tags": ["Podcast Lead"]},
                            existing_field_keys=["zhc_facebook_url"],
                            existing_tags=[])
    fb = next((f for f in dep["custom_fields"] if f["field_key"] == "zhc_facebook_url"), None)
    if not fb or fb["action"] != "reuse":
        errors.append("idempotency: pre-existing zhc_facebook_url should be reuse")
    pr = next((f for f in dep["custom_fields"] if f["field_key"] == "zhc_podcast_rating"), None)
    if not pr or pr["action"] != "create":
        errors.append("idempotency: new zhc_podcast_rating should be create")
    if not dep["tags"] or dep["tags"][0]["tag"] != "zhc_podcast_lead":
        errors.append("tag not zhc-prefixed")

    # 3. every custom field routed via Add Object Fields (never create-on-the-fly)
    if not all(f.get("add_via") == "add_object_fields" for f in fields if f["source"] == "custom"):
        errors.append("a custom field is not routed via add_object_fields")

    # 4. required + hidden are never both true
    both = _resolve_fields({"form_fields": [
        {"source": "custom", "label": "Score", "field_key": "score", "required": True, "hidden": True}]})
    if both[0]["required"] and both[0]["hidden"]:
        errors.append("required+hidden both true not corrected")

    # 5. dry-run returns expected keys + produces a click list with all phases
    with tempfile.TemporaryDirectory() as tmp:
        res = build_form(
            {"form_name": "Podcast Signup", "title": "Podcast Signup",
             "location_id": "SELFTEST_LOC", "form_fields": _reference_fields(),
             "tags": ["Podcast Lead"],
             "embed_target": {"type": "funnel", "page_id": "PAGE123"},
             "custom_css": ".hl-form{border-radius:12px}"},
            tmp, dry_run=True)
        for k in ("pages", "location_gate_ok", "plan_path", "click_list_path", "dependency_plan"):
            if k not in res:
                errors.append(f"dry-run missing key {k!r}")
        if res.get("form_url") != "" or res.get("embed_code") != "":
            errors.append("dry-run should not have a form_url/embed_code")
        cl = res.get("click_list", {})
        phases = {s["phase"] for s in cl.get("steps", [])}
        for want in ("F1", "F2", "F3", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "F13"):
            if want not in phases:
                errors.append(f"click list missing phase {want}")
        if cl.get("total_steps", 0) < 20:
            errors.append(f"click list too short: {cl.get('total_steps')}")
        # embed capture + tag handoff present
        blob = json.dumps(cl).lower()
        if "copy embed code" not in blob:
            errors.append("click list missing embed-code capture")
        if "add contact tag" not in blob:
            errors.append("click list missing tag-attachment handoff")

    # 6. no banned model tokens anywhere in the ladders
    lad = json.dumps(THINK_LADDER + EXECUTE_LADDER + QC_LADDER).lower()
    for banned in ("minimax-m2", "minimax_m2", "anthropic", "claude", "opus", "sonnet", "haiku"):
        if banned in lad:
            errors.append(f"BANNED model token in ladders: {banned}")

    # 7. never call it ConvertKit
    if "convertkit" in (json.dumps(QUICK_ADD_TAXONOMY) + " ".join(SELECTOR_STRATEGY)).lower():
        errors.append("ConvertKit mislabel leaked")

    # 8. FIELD-PLACEMENT PATH (offline, mocked browser) — drive the REAL F5/F6
    #    snapshot-and-bind code with NO browser: a fake _ab returns a live-shaped
    #    snapshot for the locate/verify steps, and a fake _perform_iframe_drag stands
    #    in for the Playwright frame-scoped coordinate-drag (whose OWN mechanism is
    #    proven in ghl_iframe_drag.py --selftest / --live-selftest). Proves placement
    #    runs end-to-end, routes the DRAG through the frame-scoped seam (NOT a
    #    top-frame `_ab drag`), AND that a genuine locate miss raises StopAndReport.
    class _FakeAB:
        def __init__(self, snapshot_text):
            self.snapshot_text = snapshot_text
            self.calls: List[tuple] = []

        def __call__(self, session, *args, timeout=30, stdin=None):
            self.calls.append(args)
            verb = args[0] if args else ""
            out = self.snapshot_text if verb == "snapshot" else ""
            return subprocess.CompletedProcess(args=list(args), returncode=0,
                                               stdout=out, stderr="")

    class _FakeDrag:
        """Stands in for _perform_iframe_drag — records each frame-scoped drag and
        returns a placed receipt (so placement continues), never a top-frame drag."""
        def __init__(self):
            self.calls: List[tuple] = []

        def __call__(self, session, source_text, drop_anchor, *, verify_text,
                     iframe_selector=GHL_FORM_IFRAME_SELECTOR, source_scroll_hint=""):
            self.calls.append((source_text, drop_anchor, verify_text, iframe_selector,
                               source_scroll_hint))
            return {"ok": True, "placed": True, "source": source_text}

    _orig_ab = globals()["_ab"]
    _orig_drag = globals()["_perform_iframe_drag"]
    _orig_smoke_first = globals()["_perform_smoke_first"]
    # B-U16 item 3: every F5 phase now runs the pre-bulk-run smoke_first() gate
    # first — the selftest's OWN offline/no-CDP shell can't satisfy it, so it
    # is stood in for here (like _perform_iframe_drag above) rather than
    # weakened: a real smoke-first STOP is proven separately below.
    globals()["_perform_smoke_first"] = lambda session, **kw: {"ok": True}
    try:
        # (a) HAPPY PATH — tiles + canvas anchors + object field all present in snapshot.
        happy = ("Form Element Quick Add Add Object Fields First Name Last Name Email "
                 "Phone Submit State City Search by Name Podcast Rating Label Query Key "
                 "Field Width Required Hidden")
        fake = _FakeAB(happy)
        fakedrag = _FakeDrag()
        globals()["_ab"] = fake
        globals()["_perform_iframe_drag"] = fakedrag
        with tempfile.TemporaryDirectory() as tmp2:
            os.makedirs(os.path.join(tmp2, "shots"), exist_ok=True)
            w: List[str] = []
            sd: List[str] = []
            sn = [0]
            std = {"source": "standard", "element": "State", "label": "State",
                   "query_key": "state", "width_pct": 50, "required": True, "hidden": False}
            cust = {"source": "custom", "element": "Rating", "label": "Podcast Rating",
                    "field_key": "zhc_podcast_rating", "field_type": "rating",
                    "required": True, "hidden": False}
            _place_quick_add_field("s", std, tmp2, sn, w, sd)
            _place_object_field("s", cust, tmp2, sn, w, sd)
            if not any(x.startswith("F5:place:State") for x in sd):
                errors.append("placement: standard field not recorded placed")
            if not any(x.startswith("F6:place:Podcast Rating") for x in sd):
                errors.append("placement: custom field not recorded placed")
            # the DRAG must route through the frame-scoped seam (>=2), NOT `_ab drag`.
            if len(fakedrag.calls) < 2:
                errors.append(f"placement: expected >=2 frame-scoped drags, got {len(fakedrag.calls)}")
            if any(c and c[0] == "drag" for c in fake.calls):
                errors.append("placement: a top-frame `_ab drag` was used (must be frame-scoped)")
            if fakedrag.calls and fakedrag.calls[0][3] != GHL_FORM_IFRAME_SELECTOR:
                errors.append("placement: frame-scoped drag used the wrong iframe selector")
            # v18.1.9: the drop target must be the ROLE-SCOPED Submit spec —
            # plain 'Submit'/'text=Submit' is ambiguous inside the iframe (the
            # Quick-Add panel's own 'Submit' category header + tile; the live
            # 2026-07-08 target-not-found).
            for c in fakedrag.calls:
                if c[1] != "role=button:Submit":
                    errors.append(f"placement: drop target must be the role-scoped "
                                  f"Submit spec, got {c[1]!r}")
            # standard field must bind Query Key (custom must NOT — locked key)
            # v18.1.3: fills go through `find label <x> fill <v>` (a bare `fill
            # <label>` positional is a CSS selector, not a label bind).
            fills = [c for c in fake.calls
                     if c and c[0] == "find" and len(c) >= 5 and c[3] == "fill"]
            if not any(c[2] == "Query Key" for c in fills):
                errors.append("placement: standard field did not bind Query Key")
            # REGRESSION LOCK (v18.1.3): no BARE text-verb may ever be emitted —
            # `click <text>` / `fill <text> <v>` / `wait -- <text>` all parse the
            # text as a CSS selector and can never match by visible text.
            for c in fake.calls:
                if not c:
                    continue
                if c[0] in ("click", "fill"):
                    errors.append(f"placement: BARE `{c[0]}` emitted (selector "
                                  f"semantics — must use `find`): {c!r}")
                if c[0] == "wait" and len(c) >= 2 and c[1] == "--":
                    errors.append(f"placement: `wait -- <text>` emitted (selector "
                                  f"semantics — must use `wait --text`): {c!r}")

        # (b) SNAPSHOT-MISS + FRAME-SCOPED SCROLL-LOCATE (the F5.locate:City fix):
        #     a tile absent from the TOP-FRAME snapshot (below the Quick-Add fold)
        #     must NOT stop the walk — the frame-scoped drag is attempted WITH the
        #     tile's category as the scroll hint (the primitive scrolls the section
        #     into view; proven in ghl_iframe_drag --selftest/--live-selftest).
        miss = _FakeAB("Form Element Quick Add Submit Email")   # no 'City' tile in snap
        missdrag = _FakeDrag()
        globals()["_ab"] = miss
        globals()["_perform_iframe_drag"] = missdrag
        with tempfile.TemporaryDirectory() as tmp3:
            os.makedirs(os.path.join(tmp3, "shots"), exist_ok=True)
            _place_quick_add_field("s", {"source": "standard", "element": "City",
                                         "label": "City", "query_key": "city",
                                         "quick_add_category": "Address",
                                         "width_pct": 100, "required": False,
                                         "hidden": False}, tmp3, [0], [], [])
            if len(missdrag.calls) != 1:
                errors.append("placement: snapshot-missing tile must still reach the "
                              f"frame-scoped drag (got {len(missdrag.calls)} calls)")
            elif missdrag.calls[0][4] != "Address":
                errors.append("placement: the tile's CATEGORY must be passed as the "
                              f"scroll hint (got {missdrag.calls[0][4]!r})")

        # (c) GENUINE MISS — the FRAME-SCOPED locate itself fails (tile absent even
        #     after the category scroll) → StopAndReport at the honest F5.locate
        #     step (never a fake success, never an un-mapped iframe-drag step).
        class _MissDrag:
            def __call__(self, session, source_text, drop_anchor, *, verify_text,
                         iframe_selector=GHL_FORM_IFRAME_SELECTOR,
                         source_scroll_hint=""):
                raise StopAndReport(
                    "iframe-drag:source-not-found",
                    "mock: tile genuinely absent inside the iframe")

        globals()["_perform_iframe_drag"] = _MissDrag()
        with tempfile.TemporaryDirectory() as tmp4:
            os.makedirs(os.path.join(tmp4, "shots"), exist_ok=True)
            raised_step = ""
            try:
                _place_quick_add_field("s", {"source": "standard", "element": "State",
                                             "label": "State", "query_key": "state",
                                             "quick_add_category": "Address",
                                             "width_pct": 100, "required": False,
                                             "hidden": False}, tmp4, [0], [], [])
            except StopAndReport as sr:
                raised_step = sr.step
            if raised_step != "F5.locate:State":
                errors.append("placement: frame-scoped locate miss must STOP at "
                              f"F5.locate:<tile> (got {raised_step!r})")

        # (d) F4 DEFAULT-FIELD RECONCILIATION (v18.1.9): the walk must DELETE the
        #     plan's unwanted defaults FOR REAL (frame-scoped, documented §6
        #     anchors) BEFORE any F5 drag — never the old warn-and-keep stub —
        #     and a genuine remove miss STOPs at the honest F4.delete step.
        class _FakeRemove:
            def __init__(self, fail=False):
                self.calls: List[str] = []
                self.fail = fail

            def __call__(self, session, field_spec, *, iframe_selector=GHL_FORM_IFRAME_SELECTOR):
                self.calls.append(field_spec)
                if self.fail:
                    raise StopAndReport("iframe-remove:remove-link-not-found",
                                        "mock: control never appeared")
                return {"ok": True, "removed": True, "already_absent": False,
                        "pre_count": 1, "post_count": 0}

        _orig_remove = globals()["_perform_iframe_field_remove"]
        f4drag = _FakeDrag()
        f4remove = _FakeRemove()
        globals()["_ab"] = _FakeAB(happy)
        globals()["_perform_iframe_drag"] = f4drag
        globals()["_perform_iframe_field_remove"] = f4remove
        try:
            with tempfile.TemporaryDirectory() as tmp5:
                os.makedirs(os.path.join(tmp5, "shots"), exist_ok=True)
                plan5 = {"location_id": "LOC", "form_name": "ZHC T",
                         "default_fields_keep": ["First Name", "Last Name", "Email"],
                         "fields": [{"source": "standard", "element": "Phone",
                                     "label": "Phone", "query_key": "phone",
                                     "width_pct": 100, "required": False,
                                     "hidden": False,
                                     "quick_add_category": "Personal Info"}]}
                cl5 = {"steps": [
                    {"phase": "F4", "action": "delete_field", "target": "Phone"},
                    {"phase": "F4", "action": "delete_field", "target": "Terms & Conditions"},
                    {"phase": "F5", "action": "drag", "target": "Phone → canvas"},
                ]}
                sd5: List[str] = []
                _walk_click_list("s", cl5, plan5, tmp5, [0], [], sd5)
                if f4remove.calls != ["placeholder=+1 (555) 000-0000", "text=I consent"]:
                    errors.append(f"F4: expected the two documented §6 anchors, got {f4remove.calls}")
                if len(f4drag.calls) != 1:
                    errors.append(f"F4: the F5 drag must still run once, got {len(f4drag.calls)}")
                want_order = ["F4:delete:Phone", "F4:delete:Terms & Conditions",
                              "F5:place:Phone"]
                got_order = [s for s in sd5 if s in want_order]
                if got_order != want_order:
                    errors.append(f"F4: deletes must PRECEDE the drag in steps_done, got {sd5}")
            # a genuine remove miss STOPs honestly at F4.delete:<name> and the
            # walk never reaches the drag.
            f4drag2 = _FakeDrag()
            globals()["_perform_iframe_drag"] = f4drag2
            globals()["_perform_iframe_field_remove"] = _FakeRemove(fail=True)
            with tempfile.TemporaryDirectory() as tmp6:
                os.makedirs(os.path.join(tmp6, "shots"), exist_ok=True)
                raised = ""
                try:
                    _walk_click_list("s", cl5, plan5, tmp6, [0], [], [])
                except StopAndReport as sr:
                    raised = sr.step
                if raised != "F4.delete:Phone":
                    errors.append(f"F4: remove miss must STOP at F4.delete:Phone, got {raised!r}")
                if f4drag2.calls:
                    errors.append("F4: the walk must NOT drag past a failed default delete")
        finally:
            globals()["_perform_iframe_field_remove"] = _orig_remove
    finally:
        globals()["_ab"] = _orig_ab
        globals()["_perform_iframe_drag"] = _orig_drag
        globals()["_perform_smoke_first"] = _orig_smoke_first

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — all checks passed (no network / no browser / no skill deps)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_form_builder",
        description="GHL (Convert and Flow) FORM builder — Skill 06. GLUE, NOT THE "
                    "CLICKER. Default: --dry-run (write plan + dependency plan + click list).")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True,
                   help="Write plan + dependency plan + click list WITHOUT browser (default).")
    g.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="Live browser execution (requires Skill 6 tools/ + pre-created deps).")
    p.add_argument("--selftest", action="store_true", help="Run no-dep self-test and exit.")
    p.add_argument("--evidence-root", default="/tmp/form-run-01", metavar="DIR")
    p.add_argument("--form-name", default="New Form")
    p.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID", ""))
    p.add_argument("--tags", default="", help="Comma-separated tag names (zhc_ auto-prefixed).")
    # U8/U10 — identical flags on every Skill-6 builder.
    ghl_run_state.add_run_state_args(p)
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    started = time.monotonic()

    try:
        state = ghl_run_state.open_run_state(
            args, "ghl_form_builder", FORM_PHASES,
            argv=list(argv if argv is not None else sys.argv[1:]),
        )
    except (ghl_run_state.RunStateNotFound, ghl_run_state.RunStateCorrupt) as exc:
        print(f"--resume: {exc}", file=sys.stderr)
        return 2

    resumed = bool(args.resume)
    evidence_root = args.evidence_root
    if resumed and state.evidence_root:
        evidence_root = state.evidence_root

    task = {
        "id": "cli-form-run",
        "form_name": args.form_name,
        "location_id": args.location_id,
        "form_fields": _reference_fields(),
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
    }

    dry_run = args.dry_run
    if resumed:
        # A resume must rebuild the SAME form the dead run was building.
        saved_task = state.carry_get("task")
        if isinstance(saved_task, dict):
            task = dict(saved_task)
        saved_dry = state.carry_get("dry_run")
        if saved_dry is not None:
            dry_run = bool(saved_dry)
    else:
        state.carry_set("task", task)
        state.carry_set("dry_run", bool(dry_run))

    task["stop_after_phase"] = args.stop_after_phase

    status = ghl_run_state.STATUS_OK
    error = ""
    result: Dict[str, Any] = {}
    try:
        result = build_form(task, evidence_root, dry_run=dry_run, state=state)
    except ghl_run_state.StopAfterPhase as sap:
        status = ghl_run_state.STATUS_STOPPED
        result = {"stopped_after_phase": sap.phase, "run_id": state.run_id}
    except Exception as exc:  # noqa: BLE001
        status = ghl_run_state.STATUS_FAILED
        error = f"{type(exc).__name__}: {exc}"
        result = {"error": error}

    if status == ghl_run_state.STATUS_OK:
        if result.get("stopped_after_phase"):
            status = ghl_run_state.STATUS_STOPPED
        elif result.get("error"):
            status = ghl_run_state.STATUS_FAILED
            error = str(result["error"])
    state.finish(status, error)

    print(json.dumps(result, indent=2, default=str))

    # U10 — stderr, so the stdout JSON contract stays parseable.
    ghl_run_state.emit_run_report(
        builder="ghl_form_builder",
        run_id=state.run_id,
        status=status,
        dry_run=bool(dry_run),
        evidence_root=evidence_root,
        duration_s=time.monotonic() - started,
        script_path=__file__,
        state=state,
        state_root=args.state_root,
        error=error,
        extra_rows={"form_url": result.get("form_url") or "(none)"},
    )

    if status == ghl_run_state.STATUS_FAILED:
        # U28 (B-U14): a D6 headless-guard refusal keeps the promised exit 75
        # (ENV-MATRIX.md; ghl_builder.py's `headless-guard` subcommand) rather
        # than the generic exit-1 an ordinary build failure gets.
        if ghl_run_state.is_d6_headless_refusal(error):
            return 75
        return 1
    return 0 if result.get("location_gate_ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
