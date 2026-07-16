#!/usr/bin/env python3
"""ghl_method.py — Method-decision architecture for Skill 06 page builds.

WHAT THIS IS
------------
Three native methods exist for landing content on a GoHighLevel page:

  (a) DIRECT — HTML fragment (NOT a full document) written into a single
      GoHighLevel native customCode element, inside a complete section →
      row → column → element blob with a populated ``general.general.colors``
      theme object. Covers ~90% of pages. B1's ``new_page_blob`` produces
      the blob; this module routes to it by default.

  (b) VERCEL-EMBED — page built/hosted on Vercel, embedded as a responsive
      iframe via a customCode element. Used when the classifier scores
      ADVANCED (rich interactivity, external frameworks, etc.). The Vercel
      host must be public+embeddable (HTTP 200, no X-Frame-Options DENY, no
      restrictive frame-ancestors) before the iframe snippet is spliced in.
      ``ghl_vercel.py`` owns the deploy/assert path; this module produces
      the iframe snippet and the routing decision.

      IFRAME SURVIVAL — CONFIRMED BY LIVE PROBE (2026-06-27, authenticated
      ``/preview/`` round-trip). GoHighLevel's preview renderer does NOT strip
      ``<iframe>`` from custom-code elements: a probe page with two
      ``<iframe data-zhc src="…">`` elements rendered both verbatim
      (``document.querySelectorAll('iframe').length === 2``; ``data-zhc``
      attributes intact; ``src`` preserved). The same probe confirmed inline
      ``<script data-zhc>`` survives AND executes, external ``<link
      rel="stylesheet">`` + inline ``<style>@import…</style>`` survive and
      apply, and no element rendered blank (autosave 201, Nuxt hydrated, 0
      console errors). The earlier research worry that GHL strips iframes on
      save is therefore DISPROVEN for the preview render path, and this
      VERCEL-EMBED escape hatch is the supported route for ADVANCED pages.

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

    IFRAME SURVIVES THE PREVIEW RENDER — CONFIRMED. A live authenticated
    ``/preview/`` probe (2026-06-27) rendered ``<iframe data-zhc>`` elements
    verbatim with ``src`` intact and no stripping. This snippet is the
    supported VERCEL-EMBED carrier; do not gate it behind a sanitizer that
    bans ``<iframe>``.

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


# ── Signal derivation from raw HTML (U23/B-U9 decision-engine hardening) ──────
#
# ``classify_page`` only ever sees what the CALLER declares in ``page_spec`` --
# an HTML-only page that never declares ``js_frameworks``/``interactive``/
# ``third_party_js``/``css_fighting`` silently scores SIMPLE by default even
# when its markup obviously carries an external framework or heavy
# interactivity. ``derive_page_signals`` closes that gap: a PURE, read-only
# analyzer over the raw HTML string that infers the SAME page_spec keys
# ``classify_page`` already understands. It never calls ``classify_page``
# itself and never raises for merely "boring" HTML (a page with no advanced
# markup simply derives an empty/near-empty partial spec).
#
# The derived signals are ALWAYS merged UNDER an explicit spec
# (``merge_derived_under_explicit``) -- a caller/build-system field that IS
# declared is always trusted over the inference; the inference only fills
# GAPS the caller left silent.

import re as _re

# Known JS-framework fingerprints. A hit forces a HARD signal via
# ``js_frameworks`` (mirrors classify_page's existing hard-signal rule).
_FRAMEWORK_MARKERS: tuple[tuple[str, str], ...] = (
    ("react", "data-reactroot"),
    ("react", "react-dom"),
    ("react", "ReactDOM.render"),
    ("react", "_reactRootContainer"),
    ("next.js", "__NEXT_DATA__"),
    ("next.js", "/_next/static"),
    ("vue", "data-v-"),
    ("vue", "new Vue("),
    ("vue", "Vue.createApp"),
    ("nuxt", "__NUXT__"),
    ("nuxt", "/_nuxt/"),
    ("angular", "ng-app"),
    ("angular", "ng-controller"),
    ("angular", "angular.module("),
    ("svelte", "svelte-"),
    ("svelte", "SvelteComponent"),
)

# Known third-party JS libraries recognized from a <script src="..."> URL.
# These are SOFT signals (classify_page's multiple-third-party-lib rule) --
# distinct from a framework, which is a hard signal.
_THIRD_PARTY_LIB_MARKERS: tuple[str, ...] = (
    "jquery", "gsap", "three.js", "threejs", "chart.js", "chartjs",
    "d3.js", "d3.min.js", "swiper", "aos.js", "lottie", "anime.min.js",
    "alpine.js", "alpinejs", "framer-motion",
)

_SCRIPT_SRC_RE = _re.compile(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\']', _re.IGNORECASE)
_STYLE_BLOCK_RE = _re.compile(r'<style\b[^>]*>(.*?)</style>', _re.IGNORECASE | _re.DOTALL)
_GLOBAL_SELECTOR_RE = _re.compile(r'(?:^|[}\s])(?:html|body|\*)\s*\{', _re.IGNORECASE)
_FONT_FACE_RE = _re.compile(r'@font-face\b', _re.IGNORECASE)

# A <script src="...react.production.min.js"> style CDN filename names the
# framework directly in its path even with no inline marker present. Matches
# the framework name immediately followed by '.', '-', or '@' in the path
# (e.g. "/react.production.min.js", "/vue.global.js", "/angular.min.js",
# "/svelte.js") without false-positiving on unrelated words merely containing
# the substring (e.g. "reactive-forms.js" does NOT match — no boundary).
_FRAMEWORK_SRC_FILENAME_RE = _re.compile(
    r'(?:^|/)(react|vue|angular|svelte)[.\-@]', _re.IGNORECASE
)


def derive_page_signals(html: str) -> dict:
    """Infer a PARTIAL page_spec from raw HTML — pure, read-only, no I/O.

    Detects, purely from the markup text:
      * script-tag / library fingerprints — populates ``js_frameworks``
        (hard signal: react/vue/angular/svelte/next.js/nuxt) and
        ``third_party_js`` (soft signal: jquery/gsap/three.js/etc., matched
        against ``<script src="...">`` URLs only).
      * fetch/WebSocket/canvas/WebGL/client-routing usage — populates
        ``interactive`` with the same behavior tokens ``classify_page``
        already recognizes (``fetch``, ``websocket``, ``canvas``, ``webgl``,
        ``routing``).
      * ``!important`` density + global selectors (bare ``html{``/``body{``/
        ``*{``) + ``@font-face`` block count — populates ``css_fighting``.
      * the raw HTML itself under ``html`` — so the payload-size hard signal
        still fires correctly for a caller with no explicit ``html``/
        ``content`` field of its own (an explicit field, if present, wins in
        ``merge_derived_under_explicit`` regardless).

    Returns only the keys it actually detected something for (an entirely
    "boring" HTML string with no matches returns just ``{"html": html}``) —
    it never invents a false-positive default. NEVER calls ``classify_page``;
    NEVER raises for boring/simple HTML; PURE (no network, no filesystem).

    Args:
        html: The raw HTML string to analyze.

    Returns:
        A partial page_spec dict, ready to be merged under an explicit spec
        via ``merge_derived_under_explicit`` and passed to ``classify_page``.

    Raises:
        ``MethodDecisionError``: if ``html`` is not a string.
    """
    if not isinstance(html, str):
        raise MethodDecisionError(
            f"derive_page_signals: html must be a str, got {type(html).__name__!r}."
        )

    derived: dict[str, Any] = {}

    script_srcs = _SCRIPT_SRC_RE.findall(html)
    combined_src_lower = " ".join(script_srcs).lower()

    # ── framework detection (script src filename, script src substring, OR
    #    inline body markers) ────────────────────────────────────────────────
    frameworks_found: list[str] = []
    for src in script_srcs:
        fname_match = _FRAMEWORK_SRC_FILENAME_RE.search(src)
        if fname_match:
            fw_name = fname_match.group(1).lower()
            if fw_name not in frameworks_found:
                frameworks_found.append(fw_name)
    for fw_name, marker in _FRAMEWORK_MARKERS:
        if marker.lower() in combined_src_lower or marker in html:
            if fw_name not in frameworks_found:
                frameworks_found.append(fw_name)
    if frameworks_found:
        derived["js_frameworks"] = frameworks_found

    # ── third-party JS library detection (script src only) ────────────────────
    third_party_found: list[str] = []
    for src in script_srcs:
        src_lower = src.lower()
        for lib in _THIRD_PARTY_LIB_MARKERS:
            if lib in src_lower and lib not in third_party_found:
                third_party_found.append(lib)
    if third_party_found:
        derived["third_party_js"] = third_party_found

    # ── interactive behaviour detection ────────────────────────────────────────
    interactive_found: list[str] = []
    if "fetch(" in html:
        interactive_found.append("fetch")
    if "WebSocket(" in html:
        interactive_found.append("websocket")
    if _re.search(r'<canvas\b', html, _re.IGNORECASE):
        interactive_found.append("canvas")
    if "getContext(" in html and "webgl" in html.lower():
        interactive_found.append("webgl")
    if ("history.pushState(" in html or "react-router" in html.lower()
            or "vue-router" in html.lower()):
        interactive_found.append("routing")
    if interactive_found:
        derived["interactive"] = interactive_found

    # ── CSS-fighting density: !important, global selectors, @font-face ────────
    important_count = html.count("!important")
    style_blocks = _STYLE_BLOCK_RE.findall(html)
    style_text = "\n".join(style_blocks)
    global_selector_count = len(_GLOBAL_SELECTOR_RE.findall(style_text))
    font_face_count = len(_FONT_FACE_RE.findall(html))
    if important_count or global_selector_count or font_face_count:
        derived["css_fighting"] = {
            "important_storms": important_count,
            "global_selectors": global_selector_count,
            "font_face_blocks": font_face_count,
        }

    # ── payload bytes carrier: the raw HTML, so an explicit-html-less caller ──
    #    still gets the payload-size hard signal. explicit wins in the merge.
    derived["html"] = html

    return derived


def merge_derived_under_explicit(explicit_spec: dict | None, derived_spec: dict) -> dict:
    """Merge ``derived_spec`` (from ``derive_page_signals``) UNDER
    ``explicit_spec`` — explicit ALWAYS wins, key for key.

    A key present in BOTH keeps the explicit value untouched (the derived
    value for that key is discarded entirely — no element-wise list merging,
    no partial dict merging within a key; explicit is authoritative at the
    key level). A key present only in ``derived_spec`` is carried through
    unchanged. A key present only in ``explicit_spec`` is carried through
    unchanged. Neither input is mutated.

    Args:
        explicit_spec: The caller-declared page_spec (may be ``None`` or
            ``{}`` — an explicit spec that declares nothing).
        derived_spec: The output of ``derive_page_signals`` (or any partial
            page_spec dict).

    Returns:
        A new merged dict, ready for ``classify_page``.

    Raises:
        ``MethodDecisionError``: if ``explicit_spec`` (when not ``None``) or
            ``derived_spec`` is not a dict.
    """
    if explicit_spec is not None and not isinstance(explicit_spec, dict):
        raise MethodDecisionError(
            f"explicit_spec must be a dict or None, got {type(explicit_spec).__name__!r}."
        )
    if not isinstance(derived_spec, dict):
        raise MethodDecisionError(
            f"derived_spec must be a dict, got {type(derived_spec).__name__!r}."
        )
    merged: dict[str, Any] = dict(derived_spec)
    if explicit_spec:
        merged.update(explicit_spec)
    return merged


def classify_page_from_html(html: str, explicit_spec: dict | None = None, *,
                            threshold: int = ADVANCED_THRESHOLD,
                            max_direct_bytes: int = MAX_DIRECT_BYTES) -> MethodDecision:
    """Convenience wrapper: derive signals from ``html``, merge them UNDER
    ``explicit_spec`` (explicit wins), then classify. Pure — no I/O.

    Equivalent to::

        classify_page(
            merge_derived_under_explicit(explicit_spec, derive_page_signals(html)),
            threshold=threshold, max_direct_bytes=max_direct_bytes,
        )

    Args:
        html: The raw HTML to derive signals from.
        explicit_spec: Optional caller-declared page_spec fields that always
            win over the derived inference.
        threshold: Override ``ADVANCED_THRESHOLD``.
        max_direct_bytes: Override ``MAX_DIRECT_BYTES``.

    Returns:
        A ``MethodDecision`` exactly like ``classify_page`` returns.

    Raises:
        ``MethodDecisionError``: on invalid ``html``/``explicit_spec``, or
            (from ``classify_page``) on an invalid merged spec.
    """
    derived = derive_page_signals(html)
    merged = merge_derived_under_explicit(explicit_spec, derived)
    return classify_page(merged, threshold=threshold, max_direct_bytes=max_direct_bytes)


# ── Site-level routing aggregation (U23/B-U9 decision-engine hardening) ───────
#
# ``classify_page`` decides PER PAGE only. A complex site can split, e.g.,
# 3 pages DIRECT + 2 VERCEL — split hosting/styling that is a real production
# headache (two different rendering surfaces backing one "site"). This
# section adds the SITE-LEVEL aggregation rule: when at least
# ``SITE_ADVANCED_RATIO_THRESHOLD`` (default 50%) of a site's pages score
# ADVANCED (VERCEL_EMBED), OR the caller declares a navigation-linked
# interactive core (e.g. a persistent app shell/nav that itself needs
# client-side routing), the WHOLE SITE routes VERCEL_EMBED as one Vercel
# project — never a per-page mix. Skill-44 WIDGET routing (form/calendar
# blocks detected inside any page) is completely unaffected by this rule;
# widgets are orthogonal to the DIRECT-vs-VERCEL_EMBED page-hosting choice.
#
# ADDITIVE + FLAG-GUARDED: this rule only takes effect when
# ``GHL_SITE_LEVEL_ROUTING=1`` is set (or ``enabled=True`` is passed
# explicitly). Unset the flag to revert to today's per-page-only behavior —
# the default path when the flag is absent.

SITE_LEVEL_ROUTING_ENV_VAR = "GHL_SITE_LEVEL_ROUTING"
SITE_ADVANCED_RATIO_THRESHOLD = 0.5


def site_level_routing_enabled(env: dict | None = None) -> bool:
    """True when the ``GHL_SITE_LEVEL_ROUTING`` flag is set to ``"1"``.

    Args:
        env: Optional env dict override (default ``os.environ``).
    """
    _env = env if env is not None else os.environ
    return str(_env.get(SITE_LEVEL_ROUTING_ENV_VAR, "")).strip() == "1"


@dataclass
class SiteMethodDecision:
    """The output of ``decide_site_method`` for a whole site.

    ``overridden``: True when the site-level rule fired and every page is
        routed VERCEL_EMBED as one project, regardless of its own per-page
        decision. False means each page keeps its own per-page method.
    ``method``: ``PageMethod.VERCEL_EMBED`` when overridden, else ``None``
        (per-page routing stands — there is no single site method to name).
    ``advanced_page_count`` / ``total_page_count`` / ``advanced_page_ratio``:
        the raw counts and ratio the rule was evaluated against.
    ``nav_linked_interactive_core``: the caller-declared flag as evaluated.
    ``ratio_threshold``: the threshold used at decision time.
    ``per_page_methods``: ``{page_name: method_value}`` snapshot of each
        page's OWN classify_page decision (audit trail — always recorded,
        whether or not the override fires).
    ``reason``: human-readable sentence explaining the decision.
    ``decided_at``: ISO-8601 timestamp string.
    """
    overridden: bool
    method: PageMethod | None
    advanced_page_count: int
    total_page_count: int
    advanced_page_ratio: float
    nav_linked_interactive_core: bool
    ratio_threshold: float
    per_page_methods: dict[str, str]
    reason: str
    decided_at: str = field(default_factory=lambda: _now())


def decide_site_method(
    page_decisions: dict[str, "MethodDecision"],
    *,
    nav_linked_interactive_core: bool = False,
    ratio_threshold: float = SITE_ADVANCED_RATIO_THRESHOLD,
    enabled: bool | None = None,
    env: dict | None = None,
) -> SiteMethodDecision:
    """Decide whether a whole site routes VERCEL_EMBED as one project.

    ``page_decisions`` MUST be a non-empty dict of ``page_name ->
    MethodDecision`` (i.e. every page's own ``classify_page`` output —
    caller classifies each page first, this function only aggregates).

    Trigger: ``enabled`` AND (``advanced_page_ratio >= ratio_threshold`` OR
    ``nav_linked_interactive_core``). When disabled (the default — see
    ``site_level_routing_enabled``), this function still computes and
    returns the full ratio/audit picture but ``overridden`` is always False
    and ``method`` is always None — a caller inspecting the decision can see
    exactly what WOULD have happened without the flag changing behavior.

    Args:
        page_decisions: ``{page_name: MethodDecision}`` for every page in
            the site (from ``classify_page``/``classify_page_from_html``).
        nav_linked_interactive_core: True when the caller has determined the
            site has a persistent navigation-linked interactive core.
        ratio_threshold: Override ``SITE_ADVANCED_RATIO_THRESHOLD``.
        enabled: Override the ``GHL_SITE_LEVEL_ROUTING`` flag explicitly
            (``None`` reads the flag via ``site_level_routing_enabled``).
        env: Optional env dict override, forwarded to
            ``site_level_routing_enabled`` when ``enabled`` is ``None``.

    Returns:
        A ``SiteMethodDecision``.

    Raises:
        ``MethodDecisionError``: if ``page_decisions`` is not a non-empty
            dict of ``MethodDecision`` values.
    """
    if not isinstance(page_decisions, dict) or not page_decisions:
        raise MethodDecisionError(
            "page_decisions must be a non-empty dict of page_name -> "
            "MethodDecision (from classify_page) — cannot make a site-level "
            "routing decision with zero pages."
        )
    for name, dec in page_decisions.items():
        if not isinstance(dec, MethodDecision):
            raise MethodDecisionError(
                f"page_decisions[{name!r}] must be a MethodDecision (from "
                f"classify_page), got {type(dec).__name__!r}."
            )

    is_enabled = site_level_routing_enabled(env) if enabled is None else bool(enabled)

    per_page_methods = {name: dec.method.value for name, dec in page_decisions.items()}
    total = len(page_decisions)
    advanced = sum(
        1 for dec in page_decisions.values() if dec.method == PageMethod.VERCEL_EMBED
    )
    ratio = advanced / total

    if not is_enabled:
        return SiteMethodDecision(
            overridden=False,
            method=None,
            advanced_page_count=advanced,
            total_page_count=total,
            advanced_page_ratio=ratio,
            nav_linked_interactive_core=bool(nav_linked_interactive_core),
            ratio_threshold=ratio_threshold,
            per_page_methods=per_page_methods,
            reason=(
                f"site-level routing disabled ({SITE_LEVEL_ROUTING_ENV_VAR} not set) — "
                f"{advanced}/{total} pages scored ADVANCED ({ratio:.0%}); each page "
                "keeps its own per-page method decision. Skill-44 widget routing is "
                "unaffected either way."
            ),
        )

    ratio_trigger = ratio >= ratio_threshold
    trigger = ratio_trigger or nav_linked_interactive_core

    if not trigger:
        return SiteMethodDecision(
            overridden=False,
            method=None,
            advanced_page_count=advanced,
            total_page_count=total,
            advanced_page_ratio=ratio,
            nav_linked_interactive_core=bool(nav_linked_interactive_core),
            ratio_threshold=ratio_threshold,
            per_page_methods=per_page_methods,
            reason=(
                f"no site-level override — {advanced}/{total} pages ({ratio:.0%}) "
                f"scored ADVANCED, below the {ratio_threshold:.0%} threshold, and no "
                "navigation-linked interactive core was declared. Each page keeps "
                "its own per-page method decision."
            ),
        )

    if ratio_trigger and nav_linked_interactive_core:
        why = (
            f"{advanced}/{total} pages ({ratio:.0%}) scored ADVANCED >= "
            f"{ratio_threshold:.0%} threshold, AND a navigation-linked interactive "
            "core was declared"
        )
    elif ratio_trigger:
        why = f"{advanced}/{total} pages ({ratio:.0%}) scored ADVANCED >= {ratio_threshold:.0%} threshold"
    else:
        why = "a navigation-linked interactive core was declared"

    return SiteMethodDecision(
        overridden=True,
        method=PageMethod.VERCEL_EMBED,
        advanced_page_count=advanced,
        total_page_count=total,
        advanced_page_ratio=ratio,
        nav_linked_interactive_core=bool(nav_linked_interactive_core),
        ratio_threshold=ratio_threshold,
        per_page_methods=per_page_methods,
        reason=(
            f"SITE-LEVEL OVERRIDE -> VERCEL_EMBED for the whole site ({why}); "
            "split hosting/styling across DIRECT + VERCEL pages is avoided by "
            "routing the whole site as one Vercel project. Skill-44 widget "
            "routing (form/calendar blocks) is unaffected."
        ),
    )


def decide_and_record_site(
    page_decisions: dict[str, "MethodDecision"],
    run_dir: str,
    *,
    nav_linked_interactive_core: bool = False,
    ratio_threshold: float = SITE_ADVANCED_RATIO_THRESHOLD,
    enabled: bool | None = None,
    env: dict | None = None,
) -> SiteMethodDecision:
    """Decide the site-level routing override and write the audit record to
    ``<run_dir>/routing/site-method-decision.json``.

    Args:
        page_decisions: Same as ``decide_site_method``.
        run_dir: The run evidence root directory. The routing subdirectory
            is created if absent.
        nav_linked_interactive_core / ratio_threshold / enabled / env: Same
            as ``decide_site_method``.

    Returns:
        The ``SiteMethodDecision`` (also written to disk for the audit
        trail).

    Raises:
        ``MethodDecisionError``: on invalid ``page_decisions``.
        ``ValueError``: if ``run_dir`` is empty.
    """
    if not run_dir or not str(run_dir).strip():
        raise ValueError("run_dir is required (the run evidence root directory).")

    decision = decide_site_method(
        page_decisions,
        nav_linked_interactive_core=nav_linked_interactive_core,
        ratio_threshold=ratio_threshold,
        enabled=enabled,
        env=env,
    )

    routing_dir = os.path.join(str(run_dir), "routing")
    os.makedirs(routing_dir, exist_ok=True)
    record_path = os.path.join(routing_dir, "site-method-decision.json")

    record = {
        "overridden": decision.overridden,
        "method": decision.method.value if decision.method is not None else None,
        "advanced_page_count": decision.advanced_page_count,
        "total_page_count": decision.total_page_count,
        "advanced_page_ratio": decision.advanced_page_ratio,
        "nav_linked_interactive_core": decision.nav_linked_interactive_core,
        "ratio_threshold": decision.ratio_threshold,
        "per_page_methods": decision.per_page_methods,
        "reason": decision.reason,
        "decided_at": decision.decided_at,
    }
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    return decision


# ── Per-client brand/theme (parameterize general.general.colors) ──────────────
#
# GoHighLevel's renderer reads ``blob['general']['general']['colors']`` — an
# 18-entry list of ``{label, value}`` dicts (NOT a ``defaultSettings.colors``
# object; that key does not exist in real GHL page blobs). The renderer crashes
# with ``Cannot read properties of undefined (reading 'colors')`` (HTTP 500) if
# this list is absent. ``ghl_rest_canvas._FLAT_THEME_COLORS`` is the canonical
# default palette and ``ghl_rest_canvas.new_page_blob`` writes it verbatim today.
#
# These helpers let a build inject a CLIENT palette while KEEPING THE EXACT
# 18-entry shape and label order GoHighLevel expects — overriding only the
# values the client supplied, never adding/removing entries. The canonical
# caller is ``new_page_blob`` (in ghl_rest_canvas.py): it passes its own
# authoritative ``_FLAT_THEME_COLORS`` as ``base`` so this module never has to
# duplicate-and-drift the source of truth.

# The 18 canonical theme labels, in GoHighLevel's required order. The CSS custom
# property for each is the lower-cased label (``--primary``, ``--secondary``, …).
THEME_COLOR_LABELS = (
    "Transparent", "Primary", "Secondary", "White", "Gray", "Black", "Red",
    "Orange", "Yellow", "Green", "Teal", "Malibu", "Indigo", "Purple", "Pink",
    "Cobalt", "Smoke", "Overlay",
)

# A built-in copy of the canonical default palette, kept ONLY as a fallback for
# ``base=None`` callers and tests. The authoritative source is
# ``ghl_rest_canvas._FLAT_THEME_COLORS``; production callers pass that as ``base``.
_DEFAULT_THEME_COLORS = [
    {"label": "Transparent", "value": "transparent"},
    {"label": "Primary", "value": "#37ca37"},
    {"label": "Secondary", "value": "#188bf6"},
    {"label": "White", "value": "#ffffff"},
    {"label": "Gray", "value": "#cbd5e0"},
    {"label": "Black", "value": "#000000"},
    {"label": "Red", "value": "#e93d3d"},
    {"label": "Orange", "value": "#f6ad55"},
    {"label": "Yellow", "value": "#faf089"},
    {"label": "Green", "value": "#9ae6b4"},
    {"label": "Teal", "value": "#81e6d9"},
    {"label": "Malibu", "value": "#63b3ed"},
    {"label": "Indigo", "value": "#757BBD"},
    {"label": "Purple", "value": "#d6bcfa"},
    {"label": "Pink", "value": "#fbb6ce"},
    {"label": "Cobalt", "value": "#155eef"},
    {"label": "Smoke", "value": "#f5f5f5"},
    {"label": "Overlay", "value": "rgba(0, 0, 0, 0.5)"},
]


class ThemeError(ValueError):
    """Raised when a client palette would break the 18-entry colors shape:
    an unknown label, a non-string/empty override value, or a ``base`` list
    whose shape is not the canonical 18-entry ``{label, value}`` form. The
    caller MUST surface this as a build FAIL — we never silently drop a client
    color or change the entry count GoHighLevel depends on."""


def _normalize_palette_keys(palette: dict) -> dict[str, str]:
    """Lower-case + strip palette keys for case-insensitive label matching.
    Raises ThemeError on a non-dict palette or a non-string/empty value."""
    if not isinstance(palette, dict):
        raise ThemeError(
            f"palette must be a dict of label->color, got {type(palette).__name__!r}."
        )
    norm: dict[str, str] = {}
    for k, v in palette.items():
        key = str(k).strip().lower()
        if not isinstance(v, str) or not v.strip():
            raise ThemeError(
                f"palette[{k!r}] must be a non-empty color string, got {v!r}."
            )
        norm[key] = v.strip()
    return norm


def build_theme_colors(palette: dict, *, base: list | None = None) -> list[dict]:
    """Return an 18-entry ``general.general.colors`` list with the client
    ``palette`` merged onto ``base``, preserving the EXACT shape and order.

    ``palette`` maps a theme label (case-insensitive — e.g. ``"primary"``,
    ``"Secondary"``, ``"overlay"``) to a CSS color value. Only the labels the
    client supplies are overridden; every other entry keeps its ``base`` value.

    ``base`` is the canonical 18-entry list to start from. Production callers
    (``ghl_rest_canvas.new_page_blob``) MUST pass their authoritative
    ``_FLAT_THEME_COLORS`` so this function never duplicates the source of
    truth; ``base=None`` falls back to ``_DEFAULT_THEME_COLORS`` (tests only).

    Raises ``ThemeError`` if ``palette`` names a label not in ``base``, if any
    override value is not a non-empty string, or if ``base`` is not a list of
    ``{label, value}`` dicts. The returned list is ALWAYS ``len(base)`` entries
    — a client palette can never add or drop a color (that would re-introduce
    the ``reading 'colors'`` 500).
    """
    src = _DEFAULT_THEME_COLORS if base is None else base
    if not isinstance(src, list) or not src:
        raise ThemeError("base must be a non-empty list of {label, value} dicts.")

    out: list[dict] = []
    known_labels: set[str] = set()
    for i, entry in enumerate(src):
        if not isinstance(entry, dict) or "label" not in entry or "value" not in entry:
            raise ThemeError(
                f"base[{i}] must be a {{'label', 'value'}} dict, got {entry!r}."
            )
        known_labels.add(str(entry["label"]).strip().lower())
        out.append({"label": entry["label"], "value": entry["value"]})

    overrides = _normalize_palette_keys(palette)
    unknown = sorted(k for k in overrides if k not in known_labels)
    if unknown:
        raise ThemeError(
            f"palette references unknown theme label(s): {unknown}. "
            f"Valid labels (case-insensitive): "
            f"{sorted(known_labels)}. Refusing to change the 18-entry shape."
        )

    for entry in out:
        key = str(entry["label"]).strip().lower()
        if key in overrides:
            entry["value"] = overrides[key]
    return out


def apply_palette_to_page_styles(page_styles_css: str, palette: dict) -> str:
    """Rewrite the ``:root{ --primary: …; … }`` custom-property declarations in
    a ``pageStyles`` CSS string to match the client ``palette``, keeping the
    colors list and the CSS variables in sync.

    Only the ``--<label>:`` declarations whose label is in ``palette`` are
    rewritten (e.g. ``palette={'primary': '#abc'}`` rewrites ``--primary: …;``).
    Non-color vars (``--headlinefont``, ``--text-color``, etc.) are untouched
    unless explicitly present in ``palette``. Returns the rewritten CSS; the
    input is never mutated.

    Raises ``ThemeError`` on a non-string CSS input or an invalid palette.
    """
    if not isinstance(page_styles_css, str):
        raise ThemeError(
            f"page_styles_css must be a str, got {type(page_styles_css).__name__!r}."
        )
    overrides = _normalize_palette_keys(palette)
    if not overrides:
        return page_styles_css

    import re

    def _sub(match: "re.Match") -> str:
        var = match.group("var").strip().lower()
        if var in overrides:
            return f"--{match.group('var')}: {overrides[var]};"
        return match.group(0)

    # Match `--<name>: <value>;` declarations (value = anything up to the `;`).
    return re.sub(
        r"--(?P<var>[A-Za-z0-9_-]+)\s*:\s*[^;]*;",
        _sub,
        page_styles_css,
    )


# ── Idempotent re-install (detect existing ZHC page by marker → update-in-place)

class InstallTargetError(ValueError):
    """Raised when the install target cannot be resolved unambiguously — e.g.
    more than one existing page already carries the same build marker. Updating
    a random one of several duplicates is dangerous, so we fail loud and ask for
    manual cleanup rather than guess."""


@dataclass
class InstallTarget:
    """The idempotent install decision for one page.

    ``action``: ``"update"`` (re-install in place over an existing ZHC page) or
        ``"create"`` (no existing page found — make a new one).
    ``page_id``: the existing page id to update (empty when ``action='create'``).
    ``matched_by``: ``"marker"`` | ``"name"`` | ``""`` — how the existing page
        was identified.
    ``reason``: human-readable explanation for the audit trail.
    """
    action: str
    page_id: str
    matched_by: str
    reason: str


def _page_carries_marker(page: dict, marker: str, *, marker_field: str = "marker") -> bool:
    """True if ``page`` carries ``marker`` either in its explicit ``marker``
    field or embedded in its stored HTML (``rawCustomCode`` / ``html`` /
    ``content``). The marker is the unique ZHC build fingerprint."""
    if not marker:
        return False
    declared = str(page.get(marker_field) or "")
    if marker == declared or (declared and marker in declared):
        return True
    for html_key in ("rawCustomCode", "html", "content", "raw_custom_code"):
        body = page.get(html_key)
        if isinstance(body, str) and marker in body:
            return True
    return False


def resolve_install_target(
    existing_pages: list,
    marker: str,
    *,
    page_name: str = "",
    marker_field: str = "marker",
) -> InstallTarget:
    """Decide whether to UPDATE an existing ZHC page in place or CREATE a new
    one — the idempotent re-install primitive.

    Re-running a build must NOT pile up duplicate pages. This function inspects
    the sub-account's ``existing_pages`` and:

      1. UPDATE if exactly one existing page carries ``marker`` (the stable ZHC
         build fingerprint, in its ``marker`` field or its stored HTML). This is
         the idempotent re-install path: same marker → same page, updated.
      2. Raise ``InstallTargetError`` if MORE THAN ONE existing page carries the
         marker (ambiguous — a prior run left duplicates; manual cleanup needed).
      3. Else, if ``page_name`` is given and exactly one existing page has that
         exact name, UPDATE it (``matched_by='name'``) — a softer fallback for
         pages created before markers were stamped.
      4. Else CREATE.

    For idempotency the caller MUST pass a STABLE marker (derived from the
    funnel/page slug), NOT a per-run nonce — otherwise every run looks new and
    re-creates the page. ``existing_pages`` items are dicts carrying at least an
    id (``id`` or ``page_id``) and optionally ``name`` / ``marker`` / stored HTML.

    Raises ``InstallTargetError`` on ambiguous matches or a missing id on the
    matched page; ``ValueError`` if ``marker`` is empty.
    """
    if not marker or not str(marker).strip():
        raise ValueError("marker is required (the stable ZHC build fingerprint).")
    if existing_pages is None:
        existing_pages = []
    if not isinstance(existing_pages, list):
        raise InstallTargetError(
            f"existing_pages must be a list, got {type(existing_pages).__name__!r}."
        )

    def _pid(p: dict) -> str:
        return str(p.get("id") or p.get("page_id") or "")

    marker_hits = [
        p for p in existing_pages
        if isinstance(p, dict) and _page_carries_marker(p, marker, marker_field=marker_field)
    ]
    if len(marker_hits) > 1:
        ids = [_pid(p) for p in marker_hits]
        raise InstallTargetError(
            f"AMBIGUOUS RE-INSTALL: {len(marker_hits)} existing pages carry marker "
            f"{marker!r} (ids={ids}). A prior run left duplicates — refusing to "
            "guess which to update. Remove the extras, then re-run."
        )
    if len(marker_hits) == 1:
        pid = _pid(marker_hits[0])
        if not pid:
            raise InstallTargetError(
                f"existing page carries marker {marker!r} but has no id/page_id — "
                "cannot target it for update."
            )
        return InstallTarget(
            action="update", page_id=pid, matched_by="marker",
            reason=f"existing page {pid} carries marker {marker!r}; updating in place.",
        )

    if page_name and str(page_name).strip():
        target = str(page_name).strip()
        name_hits = [
            p for p in existing_pages
            if isinstance(p, dict) and str(p.get("name") or "").strip() == target
        ]
        if len(name_hits) == 1 and _pid(name_hits[0]):
            pid = _pid(name_hits[0])
            return InstallTarget(
                action="update", page_id=pid, matched_by="name",
                reason=(
                    f"no marker match; exactly one existing page named {target!r} "
                    f"({pid}); updating in place (pre-marker page)."
                ),
            )

    return InstallTarget(
        action="create", page_id="", matched_by="",
        reason=f"no existing page carries marker {marker!r}; creating a new page.",
    )


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
    # Signal derivation from raw HTML (U23/B-U9).
    "derive_page_signals",
    "merge_derived_under_explicit",
    "classify_page_from_html",
    # Site-level routing aggregation (U23/B-U9).
    "SITE_LEVEL_ROUTING_ENV_VAR",
    "SITE_ADVANCED_RATIO_THRESHOLD",
    "site_level_routing_enabled",
    "SiteMethodDecision",
    "decide_site_method",
    "decide_and_record_site",
    # Per-client brand/theme (parameterize general.general.colors).
    "THEME_COLOR_LABELS",
    "ThemeError",
    "build_theme_colors",
    "apply_palette_to_page_styles",
    # Idempotent re-install.
    "InstallTarget",
    "InstallTargetError",
    "resolve_install_target",
]
