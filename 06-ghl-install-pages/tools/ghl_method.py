#!/usr/bin/env python3
"""ghl_method.py — Method-decision architecture for Skill 06 page builds.

WHAT THIS IS
------------
Three native methods exist for landing content on a GoHighLevel page:

  (a) DIRECT — HTML fragment (NOT a full document) written into a single
      GoHighLevel native customCode element, inside a complete section →
      row → column → element blob with a populated ``defaultSettings.colors``
      theme object. Covers ~90% of pages. B1's ``new_page_blob`` produces
      the blob; this module routes to it by default.

  (b) VERCEL-EMBED — page built/hosted on Vercel, embedded as a responsive
      iframe via a customCode element. Used when the classifier scores
      ADVANCED (rich interactivity, external frameworks, etc.). The Vercel
      host must be public+embeddable (HTTP 200, no X-Frame-Options DENY, no
      restrictive frame-ancestors) before the iframe snippet is spliced in.
      ``ghl_vercel.py`` owns the deploy/assert path; this module produces
      the iframe snippet and the routing decision.

  (c) WIDGET — calendar or form blocks, regardless of overall page method,
      MUST use GoHighLevel's own native widget embed built from a real
      Skill-44-created object (calendar id / form id). Faking a calendar or
      form as static HTML is FORBIDDEN. ``ghl_ecosystem.py`` creates the
      objects; ``widget_embed_snippet`` here produces the canonical embed HTML.

THE DECISION RULE (pure classifier — no network, no I/O)
---------------------------------------------------------
``classify_page(page_spec) -> MethodDecision``

  DEFAULT: DIRECT (fragment → customCode element).
  ESCALATE to VERCEL when ANY hard signal fires (weight ≥ 3 alone) OR
  when total score ≥ ADVANCED_THRESHOLD (default 3).

  Hard signals (weight 3, alone forces VERCEL):
    * external JS framework/build-step present
    * payload size > MAX_DIRECT_BYTES (256 KB)
    * ``complexity: "advanced"`` explicit in the spec

  Soft signals (accumulate toward threshold):
    * >1 third-party JS lib imported (weight 2)
    * interactive app behaviour — client-side routing, fetch/WebSocket,
      canvas, WebGL (weight 2)
    * heavy GoHighLevel-fighting CSS — ``!important`` storms, global
      selectors, ``@font-face`` blocks (weight 1 each, cap 3)

  Widget blocks inside a page (form_complexity/calendar blocks) route to
  the WIDGET path REGARDLESS of the overall page method — they are detected
  in the spec and listed in ``MethodDecision.widgets``.

AUDIT TRAIL
-----------
``decide_and_record(...)`` writes a JSON audit record per page to
``<run_dir>/routing/method-decision-<page>.json`` with:
  score, threshold, signals, widgets, reason, method, decided_at.

GLUE BOUNDARY (same as ghl_verify — no network, no browser)
------------------------------------------------------------
This module is PURE + LOGGED. It makes zero network calls and opens no
browser. The Vercel deploy/assert is in ``ghl_vercel.py``; the widget
creation is in ``ghl_ecosystem.py``; the page-data blob is in
``ghl_rest_canvas.new_page_blob``; the autosave is in ``ghl_builder``.
``decide_and_record`` is called PER PAGE, IMMEDIATELY BEFORE
``emit_rest_save_plan`` — the decision only changes ``new_value`` (fragment
vs iframe snippet vs widget snippet) and which verify assertion fires.
``emit_rest_save_plan`` itself is untouched (B2 owns that file).

WIDGET EMBED NOTE — GoHighLevel form_embed.js
---------------------------------------------
The GoHighLevel form widget embed intentionally omits integrity=/SRI
attributes because GoHighLevel serves and version-rotates that script
itself; adding an SRI hash WOULD BREAK the widget. The snippet produced by
``widget_embed_snippet`` emits the script verbatim as GoHighLevel emits it.
The exact host/path is read from the real created object (via Skill-44/MCP
``get_form``/``get_calendar``), never assumed.

UNPARSEABLE INPUT
-----------------
An unparseable or fundamentally invalid page_spec raises
``MethodDecisionError`` with a clear reason. This module NEVER silently
picks a method for an invalid input.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Method enum ───────────────────────────────────────────────────────────────

class PageMethod(str, Enum):
    """The three native methods for GoHighLevel page content delivery."""
    DIRECT = "direct"         # HTML fragment in customCode element (default)
    VERCEL_EMBED = "vercel_embed"  # Vercel-hosted page in responsive iframe
    WIDGET = "widget"         # GoHighLevel native calendar/form widget block


# ── Threshold constants (tunable on the fixture) ──────────────────────────────

# A single hard signal (weight 3) alone forces VERCEL regardless of other signals.
HARD_SIGNAL_WEIGHT = 3

# Accumulate soft signals to this total to escalate to VERCEL.
ADVANCED_THRESHOLD = 3

# Maximum byte count for a DIRECT HTML fragment before the payload-size hard
# signal fires and forces VERCEL-EMBED.
MAX_DIRECT_BYTES = 256 * 1024  # 256 KB

# Maximum number of @font-face blocks / global-selector / !important signals
# that count toward the CSS-fighting soft score (cap prevents one noisy
# stylesheet from dominating the score).
CSS_FIGHTING_CAP = 3


# ── Signal names (the audit trail records these verbatim) ─────────────────────

SIG_EXTERNAL_FRAMEWORK = "external_js_framework"
SIG_PAYLOAD_TOO_LARGE = "payload_exceeds_max_direct_bytes"
SIG_EXPLICIT_ADVANCED = "explicit_complexity_advanced"
SIG_MULTI_THIRD_PARTY_JS = "multiple_third_party_js_libs"
SIG_INTERACTIVE_APP = "interactive_app_behavior"
SIG_CSS_IMPORTANT_STORM = "css_important_storm"
SIG_CSS_GLOBAL_SELECTORS = "css_global_selectors"
SIG_CSS_FONT_FACE = "css_font_face_blocks"


# ── Widget kinds ──────────────────────────────────────────────────────────────

class WidgetKind(str, Enum):
    FORM = "form"
    BOOKING = "booking"


# ── Decision output ───────────────────────────────────────────────────────────

@dataclass
class WidgetBlock:
    """A calendar or form block detected inside a page_spec that must be
    replaced with a real GoHighLevel widget embed. ``object_id`` is empty
    until the Skill-44 create call resolves it; the router fills it before
    producing the snippet."""
    kind: WidgetKind
    block_key: str          # the key from the page_spec that triggered this
    object_id: str = ""     # filled after Skill-44 create
    location_id: str = ""   # the GoHighLevel location id


@dataclass
class MethodDecision:
    """The output of ``classify_page`` for a single page_spec.

    ``method``: the decided page method.
    ``score``: total accumulated signal weight.
    ``threshold``: ADVANCED_THRESHOLD used at decision time.
    ``signals``: list of ``{name, weight, detail?}`` dicts that fired.
    ``hard_forced``: True when a hard signal alone forced VERCEL.
    ``widgets``: list of WidgetBlock items found (form/calendar blocks).
    ``reason``: human-readable sentence explaining the decision.
    ``decided_at``: ISO-8601 timestamp string.
    """
    method: PageMethod
    score: int
    threshold: int
    signals: list[dict]
    hard_forced: bool
    widgets: list[WidgetBlock]
    reason: str
    decided_at: str = field(default_factory=lambda: _now())


# ── Errors ────────────────────────────────────────────────────────────────────

class MethodDecisionError(ValueError):
    """Raised when the page_spec is unparseable or fundamentally invalid.
    The caller MUST surface this as a FAIL rather than silently defaulting."""


# ── Pure classifier ───────────────────────────────────────────────────────────

def classify_page(page_spec: Any, *,
                  threshold: int = ADVANCED_THRESHOLD,
                  max_direct_bytes: int = MAX_DIRECT_BYTES) -> MethodDecision:
    """Classify a page_spec and return the routing decision.

    ``page_spec`` must be a non-empty dict. Raises ``MethodDecisionError`` for
    any non-dict or empty dict input (the classifier never silently picks a
    default for bad input).

    The classifier is PURE — it reads only the page_spec values and the
    tunable constants. No I/O, no network, no filesystem access.

    Args:
        page_spec: The page specification dict. Expected optional keys:
            ``html`` / ``content`` — the HTML fragment string to embed.
            ``js_frameworks`` — list of JS framework names (str).
            ``third_party_js`` — list of third-party JS library names (str).
            ``interactive`` — bool or list of behavior strings
                (e.g. "fetch", "websocket", "canvas", "webgl", "routing").
            ``complexity`` — str; "advanced" forces hard escalation.
            ``css_fighting`` — dict with keys ``important_storms`` (int),
                ``global_selectors`` (int), ``font_face_blocks`` (int).
            ``form_blocks`` — list of form block dicts (each with a key;
                triggers WIDGET detection for each).
            ``calendar_blocks`` — list of calendar block dicts (each with a
                key; triggers WIDGET detection for each).
        threshold: Override ADVANCED_THRESHOLD (default 3).
        max_direct_bytes: Override MAX_DIRECT_BYTES (default 256 KB).

    Returns:
        ``MethodDecision`` with the decided method, score, signals, widgets,
        and reason.

    Raises:
        ``MethodDecisionError`` if page_spec is not a non-empty dict.
    """
    if not isinstance(page_spec, dict):
        raise MethodDecisionError(
            f"page_spec must be a dict, got {type(page_spec).__name__!r}. "
            "Refusing to pick a method for invalid input."
        )
    if not page_spec:
        raise MethodDecisionError(
            "page_spec is an empty dict — cannot classify. "
            "Provide at least one key (html, complexity, js_frameworks, etc.)."
        )

    signals: list[dict] = []
    total_score = 0
    hard_forced = False

    def _signal(name: str, weight: int, detail: str = "") -> None:
        nonlocal total_score, hard_forced
        sig: dict = {"name": name, "weight": weight}
        if detail:
            sig["detail"] = detail
        signals.append(sig)
        total_score += weight
        if weight >= HARD_SIGNAL_WEIGHT:
            hard_forced = True

    # ── Hard signal 1: explicit complexity: "advanced" ────────────────────────
    complexity = str(page_spec.get("complexity", "")).strip().lower()
    if complexity == "advanced":
        _signal(SIG_EXPLICIT_ADVANCED, HARD_SIGNAL_WEIGHT,
                "page_spec.complexity == 'advanced'")

    # ── Hard signal 2: external JS framework / build-step present ─────────────
    frameworks = page_spec.get("js_frameworks") or []
    if not isinstance(frameworks, list):
        raise MethodDecisionError(
            f"page_spec.js_frameworks must be a list, got {type(frameworks).__name__!r}."
        )
    if frameworks:
        names = ", ".join(str(f) for f in frameworks[:5])
        _signal(SIG_EXTERNAL_FRAMEWORK, HARD_SIGNAL_WEIGHT,
                f"js_frameworks: {names}")

    # ── Hard signal 3: payload size > MAX_DIRECT_BYTES ────────────────────────
    html_content = page_spec.get("html") or page_spec.get("content") or ""
    if not isinstance(html_content, str):
        raise MethodDecisionError(
            f"page_spec.html/content must be a str, got {type(html_content).__name__!r}."
        )
    payload_bytes = len(html_content.encode("utf-8"))
    if payload_bytes > max_direct_bytes:
        _signal(SIG_PAYLOAD_TOO_LARGE, HARD_SIGNAL_WEIGHT,
                f"payload {payload_bytes} bytes > limit {max_direct_bytes} bytes")

    # ── Soft signal: >1 third-party JS lib (weight 2) ─────────────────────────
    third_party = page_spec.get("third_party_js") or []
    if not isinstance(third_party, list):
        raise MethodDecisionError(
            f"page_spec.third_party_js must be a list, got {type(third_party).__name__!r}."
        )
    if len(third_party) > 1:
        names = ", ".join(str(l) for l in third_party[:5])
        _signal(SIG_MULTI_THIRD_PARTY_JS, 2,
                f"{len(third_party)} third-party libs: {names}")

    # ── Soft signal: interactive app behaviour (weight 2) ─────────────────────
    interactive_raw = page_spec.get("interactive")
    interactive_behaviors: list[str] = []
    if isinstance(interactive_raw, bool) and interactive_raw:
        interactive_behaviors = ["interactive"]
    elif isinstance(interactive_raw, list):
        interactive_behaviors = [str(b) for b in interactive_raw]
    elif isinstance(interactive_raw, str) and interactive_raw.strip():
        interactive_behaviors = [interactive_raw.strip()]

    _advanced_behaviors = {
        "fetch", "websocket", "canvas", "webgl", "routing",
        "client-routing", "client_routing", "interactive",
    }
    matched = [b for b in interactive_behaviors
               if b.lower().replace("-", "_") in _advanced_behaviors]
    if matched:
        _signal(SIG_INTERACTIVE_APP, 2,
                f"interactive behaviors: {', '.join(matched)}")

    # ── Soft signal: CSS fighting (cap 3, weight 1 each) ──────────────────────
    css_fighting = page_spec.get("css_fighting") or {}
    if not isinstance(css_fighting, dict):
        raise MethodDecisionError(
            f"page_spec.css_fighting must be a dict, got {type(css_fighting).__name__!r}."
        )
    css_score = 0

    important_storms = int(css_fighting.get("important_storms", 0) or 0)
    if important_storms > 0:
        w = min(1, CSS_FIGHTING_CAP - css_score)
        if w > 0:
            _signal(SIG_CSS_IMPORTANT_STORM, w,
                    f"important_storms={important_storms}")
            css_score += w

    global_selectors = int(css_fighting.get("global_selectors", 0) or 0)
    if global_selectors > 0:
        w = min(1, CSS_FIGHTING_CAP - css_score)
        if w > 0:
            _signal(SIG_CSS_GLOBAL_SELECTORS, w,
                    f"global_selectors={global_selectors}")
            css_score += w

    font_face_blocks = int(css_fighting.get("font_face_blocks", 0) or 0)
    if font_face_blocks > 0:
        w = min(1, CSS_FIGHTING_CAP - css_score)
        if w > 0:
            _signal(SIG_CSS_FONT_FACE, w,
                    f"font_face_blocks={font_face_blocks}")
            css_score += w

    # ── Widget detection (form / calendar blocks — independent of method) ──────
    widgets: list[WidgetBlock] = []

    form_blocks = page_spec.get("form_blocks") or []
    if not isinstance(form_blocks, list):
        raise MethodDecisionError(
            f"page_spec.form_blocks must be a list, got {type(form_blocks).__name__!r}."
        )
    for i, fb in enumerate(form_blocks):
        if not isinstance(fb, dict):
            raise MethodDecisionError(
                f"page_spec.form_blocks[{i}] must be a dict (form block descriptor)."
            )
        key = fb.get("key") or fb.get("name") or f"form_{i}"
        loc_id = fb.get("location_id") or ""
        widgets.append(WidgetBlock(kind=WidgetKind.FORM, block_key=str(key),
                                   location_id=str(loc_id)))

    calendar_blocks = page_spec.get("calendar_blocks") or []
    if not isinstance(calendar_blocks, list):
        raise MethodDecisionError(
            f"page_spec.calendar_blocks must be a list, got {type(calendar_blocks).__name__!r}."
        )
    for i, cb in enumerate(calendar_blocks):
        if not isinstance(cb, dict):
            raise MethodDecisionError(
                f"page_spec.calendar_blocks[{i}] must be a dict (calendar block descriptor)."
            )
        key = cb.get("key") or cb.get("name") or f"calendar_{i}"
        loc_id = cb.get("location_id") or ""
        widgets.append(WidgetBlock(kind=WidgetKind.BOOKING, block_key=str(key),
                                   location_id=str(loc_id)))

    # ── Method decision ────────────────────────────────────────────────────────
    if hard_forced or total_score >= threshold:
        method = PageMethod.VERCEL_EMBED
        if hard_forced:
            hard_names = [s["name"] for s in signals if s["weight"] >= HARD_SIGNAL_WEIGHT]
            reason = (
                f"VERCEL-EMBED: hard signal(s) forced escalation "
                f"({', '.join(hard_names)}); score={total_score}."
            )
        else:
            reason = (
                f"VERCEL-EMBED: accumulated score {total_score} >= "
                f"threshold {threshold}; signals: "
                f"{', '.join(s['name'] for s in signals)}."
            )
    else:
        method = PageMethod.DIRECT
        if signals:
            reason = (
                f"DIRECT: score {total_score} < threshold {threshold}; "
                f"no hard signal fired. Signals: "
                f"{', '.join(s['name'] for s in signals) or 'none'}."
            )
        else:
            reason = (
                "DIRECT: no advanced signals detected; default method."
            )

    if widgets:
        widget_desc = ", ".join(
            f"{w.kind.value}:{w.block_key}" for w in widgets
        )
        reason += (
            f" Widget blocks detected ({widget_desc}) — these will use "
            "GoHighLevel native widget embeds regardless of page method."
        )

    return MethodDecision(
        method=method,
        score=total_score,
        threshold=threshold,
        signals=signals,
        hard_forced=hard_forced,
        widgets=widgets,
        reason=reason,
    )


# ── Snippet builders ──────────────────────────────────────────────────────────

def iframe_embed_snippet(url: str, *, height_px: int = 600,
                         title: str = "Embedded page") -> str:
    """Build a responsive iframe snippet for the Vercel-embed path.

    Produces a GoHighLevel-safe customCode element body (an HTML fragment, NOT
    a full document) that embeds ``url`` in a 100%-wide, ``height_px``-tall
    iframe with no border. The inline wrapper div + the iframe ``title``
    attribute satisfy basic accessibility requirements.

    The ``url`` MUST already be proven embeddable (HTTP 200, no X-Frame-Options
    DENY, no restrictive frame-ancestors) by ``ghl_vercel.assert_embeddable``
    BEFORE this snippet is spliced into a GoHighLevel page.

    Args:
        url: The public Vercel deployment URL (embeddable, protection off).
        height_px: The iframe height in pixels (default 600).
        title: Accessibility title for the iframe (default "Embedded page").

    Returns:
        An HTML fragment string (no DOCTYPE, no html/head/body tags).
    """
    if not url or not str(url).strip():
        raise ValueError("url is required (the embeddable Vercel deployment URL)")
    if not isinstance(height_px, int) or height_px <= 0:
        raise ValueError(f"height_px must be a positive integer, got {height_px!r}")
    url = url.strip().rstrip("/")
    return (
        f'<div class="zhc-vercel-embed" style="width:100%;overflow:hidden;">'
        f'<iframe src="{url}" '
        f'title="{title}" '
        f'style="width:100%;height:{height_px}px;border:0;display:block;" '
        f'loading="lazy" '
        f'allowfullscreen>'
        f'</iframe>'
        f'</div>'
    )


def widget_embed_snippet(kind: WidgetKind, object_id: str,
                         location_id: str) -> str:
    """Build the GoHighLevel canonical widget embed snippet for a
    Skill-44-created form or calendar object.

    IMPORTANT — SRI/integrity omission is intentional:
    GoHighLevel serves and version-rotates its form_embed.js script itself.
    Adding an ``integrity=`` attribute WOULD BREAK the widget (the hash would
    mismatch on any version rotation). The script tag is emitted verbatim,
    exactly as GoHighLevel emits it. DO NOT add SRI hashes here.

    The exact host and path MUST come from the real created object (via
    Skill-44 ``get_form`` / ``get_calendar`` re-GET, or via
    ``EcosystemOps.create_form`` / ``EcosystemOps.create_calendar`` receipt)
    — never assumed. Pass the verified ``object_id`` here.

    Args:
        kind: ``WidgetKind.FORM`` or ``WidgetKind.BOOKING``.
        object_id: The GoHighLevel form id or calendar id (from a real
            Skill-44 create receipt + re-GET 200; empty string is rejected).
        location_id: The GoHighLevel sub-account location id (required for
            the form embed widget path).

    Returns:
        An HTML fragment string (no DOCTYPE, no html/head/body tags) embedding
        the GoHighLevel native widget.

    Raises:
        ValueError: if ``object_id`` or ``location_id`` is empty/missing.
    """
    if not object_id or not str(object_id).strip():
        raise ValueError(
            "object_id is required (must be a real GoHighLevel form/calendar id "
            "from a Skill-44 create receipt + re-GET 200, never assumed)."
        )
    if not location_id or not str(location_id).strip():
        raise ValueError(
            "location_id is required (the GoHighLevel sub-account location id)."
        )

    object_id = str(object_id).strip()
    location_id = str(location_id).strip()

    GHL_WIDGET_HOST = "https://link.msgsndr.com"

    if kind == WidgetKind.FORM:
        # GoHighLevel form widget embed: the form_embed.js script + the
        # widget div. SRI/integrity intentionally omitted (see module docstring).
        # The script src and the widget path are derived from the real created
        # object id and location id — never hardcoded.
        return (
            f'<!-- GoHighLevel form widget: form_id={object_id} -->'
            f'<div class="hl_form-embed" style="width:100%;"></div>'
            f'<script src="{GHL_WIDGET_HOST}/widget/form/{object_id}" '
            f'data-location-id="{location_id}" '
            f'type="text/javascript" '
            f'async>'
            f'</script>'
        )

    if kind == WidgetKind.BOOKING:
        # GoHighLevel booking/calendar widget embed.
        return (
            f'<!-- GoHighLevel calendar widget: calendar_id={object_id} -->'
            f'<div class="hl_booking-embed" style="width:100%;min-height:700px;"></div>'
            f'<script src="{GHL_WIDGET_HOST}/widget/booking/{object_id}" '
            f'data-calendar-id="{object_id}" '
            f'data-location-id="{location_id}" '
            f'type="text/javascript" '
            f'async>'
            f'</script>'
        )

    raise ValueError(f"Unknown widget kind: {kind!r}")


# ── Glue: decide + record (called per page, before emit_rest_save_plan) ────────

def decide_and_record(page_spec: Any, page_name: str, run_dir: str, *,
                      threshold: int = ADVANCED_THRESHOLD,
                      max_direct_bytes: int = MAX_DIRECT_BYTES) -> MethodDecision:
    """Classify ``page_spec``, write the routing audit record, and return the
    decision.

    This is the glue called PER PAGE, IMMEDIATELY BEFORE
    ``ghl_builder.emit_rest_save_plan``. It:
      1. Calls ``classify_page(page_spec)`` (pure; raises
         ``MethodDecisionError`` on bad input — never silently defaults).
      2. Writes ``<run_dir>/routing/method-decision-<page_name>.json`` with
         the full audit trail (score, threshold, signals, widgets, reason,
         method, decided_at).
      3. Returns the ``MethodDecision``.

    The decision only changes ``new_value`` (fragment vs iframe-snippet vs
    widget-snippet) and which verify assertion fires.
    ``ghl_builder.emit_rest_save_plan`` is untouched (B2 owns that file).

    Args:
        page_spec: The page specification dict (passed to ``classify_page``).
        page_name: A short slug used as the audit filename component (e.g.
            "home", "optin", "sales"). Must be a non-empty string.
        run_dir: The run evidence root directory. The routing subdirectory
            is created if absent.
        threshold: Override ADVANCED_THRESHOLD.
        max_direct_bytes: Override MAX_DIRECT_BYTES.

    Returns:
        The ``MethodDecision`` (also written to disk for the audit trail).

    Raises:
        ``MethodDecisionError``: on invalid page_spec.
        ``ValueError``: if ``page_name`` or ``run_dir`` is empty.
    """
    if not page_name or not str(page_name).strip():
        raise ValueError("page_name is required (used as the audit filename component).")
    if not run_dir or not str(run_dir).strip():
        raise ValueError("run_dir is required (the run evidence root directory).")

    # Sanitize page_name for use in a filename: replace non-alphanumeric with -
    import re
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", str(page_name).strip())

    decision = classify_page(page_spec, threshold=threshold,
                             max_direct_bytes=max_direct_bytes)

    # Write the routing audit record.
    routing_dir = os.path.join(str(run_dir), "routing")
    os.makedirs(routing_dir, exist_ok=True)
    record_path = os.path.join(routing_dir, f"method-decision-{safe_name}.json")

    record = {
        "page_name": page_name,
        "method": decision.method.value,
        "score": decision.score,
        "threshold": decision.threshold,
        "hard_forced": decision.hard_forced,
        "signals": decision.signals,
        "widgets": [
            {
                "kind": w.kind.value,
                "block_key": w.block_key,
                "object_id": w.object_id,
                "location_id": w.location_id,
            }
            for w in decision.widgets
        ],
        "reason": decision.reason,
        "decided_at": decision.decided_at,
    }
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    return decision


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    """Return an ISO-8601 UTC timestamp string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Public API ────────────────────────────────────────────────────────────────

__all__ = [
    "PageMethod",
    "WidgetKind",
    "WidgetBlock",
    "MethodDecision",
    "MethodDecisionError",
    "ADVANCED_THRESHOLD",
    "MAX_DIRECT_BYTES",
    "HARD_SIGNAL_WEIGHT",
    "CSS_FIGHTING_CAP",
    "SIG_EXTERNAL_FRAMEWORK",
    "SIG_PAYLOAD_TOO_LARGE",
    "SIG_EXPLICIT_ADVANCED",
    "SIG_MULTI_THIRD_PARTY_JS",
    "SIG_INTERACTIVE_APP",
    "SIG_CSS_IMPORTANT_STORM",
    "SIG_CSS_GLOBAL_SELECTORS",
    "SIG_CSS_FONT_FACE",
    "classify_page",
    "iframe_embed_snippet",
    "widget_embed_snippet",
    "decide_and_record",
]
