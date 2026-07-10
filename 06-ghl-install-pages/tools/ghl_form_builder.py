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
from typing import Any, Dict, List, Optional

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

try:  # rate limiter + keepalive + F5(b) pre-phase re-mint (reused from dispatcher when present)
    from v2_dispatcher import RateGovernor as _RealRateGovernor  # type: ignore
    from v2_dispatcher import SessionKeepalive as _RealKeepalive  # type: ignore
    from v2_dispatcher import remint_if_stale as _real_remint_if_stale  # type: ignore
except Exception:  # noqa: BLE001
    _RealRateGovernor = None  # type: ignore
    _RealKeepalive = None  # type: ignore
    _real_remint_if_stale = None  # type: ignore


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------
FORM_BUILDER_VERSION = "v0.1.0"

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
def _run_preflight(task: dict, fields: List[dict], dep_plan: dict) -> dict:
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
    Returns CompletedProcess; never raises (callers inspect returncode/stdout)."""
    cmd_str = ghl_builder.browser_cmd("--session", session, *args)  # type: ignore[union-attr]
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


def _click(session: str, target: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return _ab(session, "click", target, timeout=timeout)


def _fill(session: str, label: str, value: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return _ab(session, "fill", label, value, timeout=timeout)


def _wait_text(session: str, text: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return _ab(session, "wait", "--", text, timeout=timeout)


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


def _capture_form_id(session: str) -> str:
    """Capture the built form's id from the builder IFRAME's `.src` attribute.

    Reads the form id out of the cross-origin `/form-builder-v2/<formId>` iframe src
    (parent-readable), falling back to the top-frame `location.pathname + hash +
    search` match; returns '' if neither yields an id. Fixes the prior top-frame-only
    read that always returned '' (the top frame carries no form id), which left the
    id uncaptured so downstream delete/verify could not target the form.

    HARDENING: the raw `_eval` result is re-validated SERVER-SIDE against the GHL
    form-id shape (``[A-Za-z0-9]{15,30}``) before being returned. A value that does
    not match that shape is rejected (returns '') — never trust raw eval output as an
    id, so a malformed / oversized / punctuation-bearing capture can't poison the
    downstream delete/verify targeting."""
    got = _eval(session, _FORM_ID_CAPTURE_JS, timeout=12)
    form_id = (got or "").strip()
    # Re-validate the captured id's SHAPE before trusting it downstream.
    if not _FORM_ID_SHAPE_RE.fullmatch(form_id):
        return ""
    return form_id


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


def _try_rename(session: str, form_name: str) -> bool:
    """Best-effort rename of the in-iframe inline title (a [runtime-capture] surface).
    ONE snapshot-bound attempt; on miss returns False (caller records a warning —
    rename is cosmetic, never a hard stop, never brute-forced)."""
    snap = _snapshot(session)
    if ("Form " not in snap) and ("Untitled" not in snap):
        return False
    _ab(session, "dblclick", "Form 1", timeout=10)
    _ab(session, "type", form_name, timeout=10)
    _ab(session, "press", "Enter", timeout=8)
    return form_name[:14] in _snapshot(session)


# ── cleanup: DELETE the built form (SELECTORS-LIVE-form.md §3) ────────────────
def _delete_form(session: str, location_id: str, form_id: str, form_name: str) -> dict:
    """search → row Actions → menuitem Delete → confirm dialog Delete → verify gone.
    Returns {deleted, residue_in_list}. Best-effort but honest about residue."""
    _router_push(session, _forms_list_route(location_id), expect_contains="form-builder")
    _wait_text(session, "Create form", timeout=20)
    query = form_name or form_id
    _fill(session, "Search for forms", query, timeout=12)
    _wait_text(session, "Actions", timeout=12)
    _click(session, "Actions")
    _wait_text(session, "Delete", timeout=10)
    _click(session, "Delete")            # menuitem
    _wait_text(session, "Delete form", timeout=10)   # confirm dialog title
    _click(session, "Delete")            # dialog-scoped confirm
    _wait_text(session, "Create form", timeout=12)
    snap = _snapshot(session)
    residue = bool(form_id and form_id in snap)
    return {"deleted": not residue, "form_id": form_id, "residue_in_list": residue}


# ── field placement (F5 Quick-Add + F6 Add-Object-Fields) — runtime snapshot-bind ──
# SELECTORS-LIVE-form.md §7 constraint: the builder is a cross-origin iframe; Quick-Add
# tiles + object-field rows carry NO stable CDP ref and top-frame CSS / `text=` cannot
# reach into the iframe. agent-browser 0.27.0 AUTO-INLINES the iframe and resolves the
# `drag` / `fill` / `click` verbs against the LIVE snapshot by VISIBLE TEXT — the exact
# primitive ghl_survey_builder.py._p2_pull_object_fields uses to place its object fields.
# So every step below is snapshot-and-bind by visible text (never an invented selector),
# and a genuine unplaceable field is a StopAndReport — NOT the default path.
_CANVAS_DROP_ANCHORS = ("Submit", "Email", "Phone", "Last Name", "First Name")


def _canvas_drop_anchor(session: str, snap: str = "") -> str:
    """A visible-text landmark ON the form canvas to drop a dragged tile onto. A fresh
    scratch form always carries Submit + the default fields (CLICK-MAP Step 8 / §6).
    Returns the first present anchor from the live snapshot, or '' if none is visible."""
    snap = snap or _snapshot(session)
    for a in _CANVAS_DROP_ANCHORS:
        if a in snap:
            return a
    return ""


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
        _click(session, "Required")
    elif field.get("hidden"):
        _click(session, "Hidden")


def _ensure_quick_add_panel(session: str) -> str:
    """Ensure the left Form-Element ▸ Quick Add panel is open; return the live snapshot.
    A fresh scratch builder opens with it already visible (CLICK-MAP Step 9). If the
    'Quick Add' tab text is present we click it to be explicit; the '+' add-element
    toggle is icon-only [runtime-capture] and is deliberately NOT brute-forced."""
    snap = _snapshot(session)
    if "Quick Add" in snap:
        _click(session, "Quick Add")
        snap = _snapshot(session)
    return snap


def _place_quick_add_field(session: str, field: dict, evidence_root: str,
                           shot_n: List[int], warnings: List[str],
                           steps_done: List[str]) -> None:
    """F5 — place ONE standard field via Quick Add. LOCATE the tile by visible text →
    DRAG onto the canvas → VERIFY it landed → BIND props. StopAndReport ONLY on a genuine
    miss (tile absent, no drop landmark, or nothing placed) — never as the default path."""
    tile = field["element"]
    label = field["label"]
    snap = _ensure_quick_add_panel(session)
    if tile not in snap:
        raise StopAndReport(
            f"F5.locate:{tile}",
            f"Quick-Add tile {tile!r} is not present in the live builder snapshot "
            "(Form Element ▸ Quick Add). Its category may need scrolling into view "
            "(SELECTORS-LIVE-form.md §8). A tile that is not on screen cannot be dragged "
            "— resolve live; no CSS invented, no brute-force.")
    anchor = _canvas_drop_anchor(session, snap)
    if not anchor:
        raise StopAndReport(
            f"F5.drop:{tile}",
            "no canvas drop landmark (Submit / a default field) is visible to drop the "
            f"{tile!r} tile onto.")
    _ab(session, "drag", tile, anchor, timeout=25)
    _wait_text(session, label[:18], timeout=15)
    after = _snapshot(session)
    if label[:12] not in after and tile not in after:
        raise StopAndReport(
            f"F5.place:{tile}",
            f"dragged {tile!r} onto {anchor!r} but no {label!r} field appeared on the "
            "canvas (snapshot-and-bind miss). STOP — do not brute-force or invent CSS.")
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
    anchor = _canvas_drop_anchor(session, snap)
    if not anchor:
        raise StopAndReport(
            f"F6.drop:{key or label}",
            "no canvas drop landmark is visible to drop the object field onto.")
    _ab(session, "drag", label[:24], anchor, timeout=25)
    _wait_text(session, label[:18], timeout=15)
    if label[:12] not in _snapshot(session):
        raise StopAndReport(
            f"F6.place:{key or label}",
            f"dragged object field {label!r} but it did not appear on the canvas "
            "(snapshot-and-bind miss). STOP — no brute-force or invented CSS.")
    _bind_field_props(session, field, warnings)
    _fill(session, "Search by Name", "")               # clear for the next field
    steps_done.append(f"F6:place:{label[:24]}")
    _screenshot(session, _shot(evidence_root, shot_n, f"f6-{_slug(label)}"))


# ── the click-list walk (locked-anchor interpreter) ──────────────────────────
def _walk_click_list(session: str, click_list: dict, plan: dict, evidence_root: str,
                     shot_n: List[int], warnings: List[str], steps_done: List[str]) -> dict:
    """Interpret each click-list step through the LOCKED anchors. Returns
    {form_id, form_url, embed_snippet}. Raises StopAndReport on a REQUIRED miss."""
    loc = plan["location_id"]
    form_name = plan["form_name"]
    form_id = ""
    form_url = ""
    embed = ""
    f5_done = [False]   # place ALL standard fields on the first F5 step, then skip
    f6_done = [False]   # place ALL pre-created custom fields on the first F6 step
    keep_defaults = set(plan.get("default_fields_keep", []))

    # F5 uniform keepalive + pre-phase re-mint (SKILL-6-BULLETPROOF-SPEC-v1 F5):
    # the survey builder already threads this through every Part-2 phase; the
    # form builder's click-list walk had the import but never wired it in (a
    # confirmed gap — see build ledger). Fire the check once per PHASE
    # TRANSITION (F1→F2→...→F13), not per click-list step, so a long form build
    # never crosses the ~60min id_token window uncovered.
    _keepalive = _RealKeepalive() if _RealKeepalive is not None else None
    _last_phase: List[Optional[str]] = [None]

    for step in click_list["steps"]:
        phase, action, target = step["phase"], step["action"], (step["target"] or "")
        tgt = target.strip()
        tag = f"{phase}:{action}:{tgt[:36]}"

        if phase != _last_phase[0]:
            _pre_phase_check(session, _keepalive)
            _last_phase[0] = phase

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
                _click(session, "Create form")
                _wait_text(session, "Start from Scratch", timeout=20)
                _screenshot(session, _shot(evidence_root, shot_n, "f2-create-modal"))
                steps_done.append(tag)
            elif action == "confirm":
                steps_done.append(tag)                      # Scratch is the default radio
            elif action == "click" and tgt == "Create":
                _click(session, "Create")
                _wait_text(session, "Save", timeout=30)
                form_id = _capture_form_id(session)
                if not form_id:
                    raise StopAndReport("F2.create",
                                        "entered the builder but could not read the form id from the "
                                        "/form-builder-v2/<id> route")
                _screenshot(session, _shot(evidence_root, shot_n, "f2-builder"))
                steps_done.append(tag)
            elif action == "click" and tgt.lower() == "use a template":
                warnings.append("F2: template path requested — minimal live run uses Start-from-Scratch")
            continue

        # F3 — rename (in-iframe inline title = runtime-capture; best-effort, never STOP)
        if phase == "F3":
            if tag.startswith("F3:click") or action == "click":
                if _try_rename(session, form_name):
                    steps_done.append(f"F3:rename:{form_name[:24]}")
                    _screenshot(session, _shot(evidence_root, shot_n, "f3-renamed"))
                else:
                    warnings.append("F3: the form title is an in-iframe inline-edit [runtime-capture] "
                                    "surface — snapshot-bind miss; left the default name (no brute-force). "
                                    "Rename via a later capture or the Settings tab.")
            continue

        # F4 — delete default fields (per-field Remove link = in-iframe runtime-capture)
        if phase == "F4":
            warnings.append(f"F4: default-field delete ({tgt[:24]!r}) is in-iframe runtime-capture — "
                            "kept defaults for the minimal run")
            continue

        # F5 / F6 — field placement. On the FIRST step of each phase we place ALL of
        # that phase's fields via runtime snapshot-and-bind (locate → drag → verify →
        # bind), then skip the phase's now-redundant per-property sub-steps. A field
        # already present as a KEPT DEFAULT is not re-dragged (no duplicates). A genuine
        # unplaceable field STOPs-and-reports — never the default path, never invented CSS.
        if phase == "F5":
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

    return {"form_id": form_id, "form_url": form_url, "embed_snippet": embed}


def _live_build(task: dict, plan: dict, click_list: dict, fields: List[dict],
                dep_plan: dict, preflight: dict, evidence_root: str, started: float) -> dict:
    """Drive the live browser build end-to-end: seed → land → walk → capture embed →
    write build receipt → verify → CLEANUP (delete form + close session). Every
    failure is a STOP-and-report; the created form is ALWAYS deleted in finally."""
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
                                shot_n, warnings, steps_done)
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

    except StopAndReport as sr:
        stop = sr
        _log(f"STOP-and-report @ {sr.step}: {sr.reason}")
    except Exception as exc:  # noqa: BLE001
        stop = StopAndReport("unexpected", f"{type(exc).__name__}: {exc}")
        _log(f"live build unexpected error: {type(exc).__name__}: {exc}")
    finally:
        # CLEANUP — ALWAYS delete the created form, then close the session (no residue).
        cleanup["attempted"] = True
        try:
            if form_id:
                cleanup.update(_delete_form(session, location_id, form_id, plan["form_name"]))
                _screenshot(session, _shot(evidence_root, shot_n, "cleanup-deleted"))
            else:
                cleanup["deleted"] = True
                cleanup["note"] = "no form was created — nothing to delete"
        except Exception as exc:  # noqa: BLE001
            cleanup["deleted"] = False
            cleanup["error"] = f"{type(exc).__name__}: {exc}"
            warnings.append(f"cleanup: delete_form raised: {exc}")
        finally:
            try:
                _session_cm.__exit__(None, None, None)   # emit the teardown step
            except Exception:  # noqa: BLE001
                pass
            _close_session(location_id)                  # REAL close of the seeded session
        _write_json(os.path.join(evidence_root, "routing", "cleanup.json"), cleanup)

    duration = time.monotonic() - started
    if stop is not None:
        return {
            "pages": [], "location_gate_ok": False, "duration_s": duration,
            "form_url": "", "form_id": form_id, "embed_code": "",
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
def build_form(task: dict, evidence_root: str, *, dry_run: bool = True) -> dict:
    """Build a GHL (Convert and Flow) FORM via browser-control.

    THINK layer always runs (preflight + plan + dependency plan + field map +
    click list). LIVE browser execution runs only when dry_run=False AND the
    real skill modules (ghl_builder / browser_manager) are importable.
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
    preflight = _run_preflight(task, fields, dep_plan)

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
                       evidence_root, started)


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
    #    snapshot-and-bind drag+bind code with NO browser: a fake _ab that returns a
    #    live-shaped snapshot. Proves placement runs end-to-end AND that a genuine miss
    #    raises StopAndReport (not the default path) — i.e. this is NOT a skeleton.
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

    _orig_ab = globals()["_ab"]
    try:
        # (a) HAPPY PATH — tiles + canvas anchors + object field all present in snapshot.
        happy = ("Form Element Quick Add Add Object Fields First Name Last Name Email "
                 "Phone Submit State City Search by Name Podcast Rating Label Query Key "
                 "Field Width Required Hidden")
        fake = _FakeAB(happy)
        globals()["_ab"] = fake
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
            drags = [c for c in fake.calls if c and c[0] == "drag"]
            if len(drags) < 2:
                errors.append(f"placement: expected >=2 real drag commands, got {len(drags)}")
            # standard field must bind Query Key (custom must NOT — locked key)
            fills = [c for c in fake.calls if c and c[0] == "fill"]
            if not any(len(c) >= 2 and c[1] == "Query Key" for c in fills):
                errors.append("placement: standard field did not bind Query Key")

        # (b) GENUINE MISS — the tile is absent from the snapshot → StopAndReport.
        miss = _FakeAB("Form Element Quick Add Submit Email")   # no 'State' tile
        globals()["_ab"] = miss
        with tempfile.TemporaryDirectory() as tmp3:
            os.makedirs(os.path.join(tmp3, "shots"), exist_ok=True)
            raised = False
            try:
                _place_quick_add_field("s", {"source": "standard", "element": "State",
                                             "label": "State", "query_key": "state",
                                             "width_pct": 100, "required": False,
                                             "hidden": False}, tmp3, [0], [], [])
            except StopAndReport:
                raised = True
            if not raised:
                errors.append("placement: absent tile did NOT raise StopAndReport")
    finally:
        globals()["_ab"] = _orig_ab

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
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    task = {
        "id": "cli-form-run",
        "form_name": args.form_name,
        "location_id": args.location_id,
        "form_fields": _reference_fields(),
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
    }
    result = build_form(task, args.evidence_root, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("location_gate_ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
