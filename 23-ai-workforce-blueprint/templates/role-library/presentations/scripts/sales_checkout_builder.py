#!/usr/bin/env python3
"""
sales_checkout_builder.py — the sales-page + checkout-page executor (Wave C, C2).

TEMPLATES the Loop 2C flow (proven by hand 2026-08-07, render-verified):
    kie.ai design  ->  agent copy  ->  HTML  ->  GHL funnel push (Skill 6, token-only REST)
See GAUNTLET-LOOP-WORK/LOOP2C-VSL-SALES-CHECKOUT-WEBSITE.md. This module templates the
FLOW ONLY — it carries no client name, no client copy, no funnel id, no branding. Every
client-specific value (brand colors, offer copy, funnel name) is resolved at runtime from
the run's own intake.json, exactly like workbook_builder.py resolves brand/client per run.

THE GATE — WANT_SALES_CHECKOUT (upsell-questions.json v1.0.0, U026 waiver mechanic)
-------------------------------------------------------------------------------------
Read from working/copy/intake.json's `pre_presentation_capture.WANT_SALES_CHECKOUT`
(intake_writer.py's ID_TO_FIELD/PRE_CAPTURE_FIELDS mapping — the SAME field the app writes).
Per upsell-questions.json's `waiver_field_mapping.sales_checkout` (toggle=want_sales_checkout,
reason=sales_checkout_declined_reason): a "no" is a CLIENT WAIVER and REQUIRES the client's
own verbatim declined-reason (`SALES_CHECKOUT_DECLINED_REASON`) — "it is never inferred from
silence and never written by the assistant." Four outcomes, never conflated:
    ABSENT / BLANK           -> DEFER   (never treated as a decline; the question was never
                                          asked/answered in this run — nothing to gate on yet)
    "yes"                    -> BUILD
    "no" + real quote        -> WAIVED  (legitimately gated OUT; not a failure)
    "no" + missing/blank quote,
    or any unrecognized value -> FAIL CLOSED (a self-authored "no" is refused, mirrors
                                          presentation_job/waivers.py's own
                                          client_request_quote >= 3-char floor)

THE GHL PUSH — WHY THIS IS A DELEGATED RECEIPT, NOT A LIVE DRIVE
-------------------------------------------------------------------------------------
06-ghl-install-pages/tools/ghl_rest_canvas.py is "THE GLUE, NOT THE CLICKER": its own
docstring states plainly that every /funnels/* route is Cloudflare-WAF-gated and MUST run
"from inside the agent-browser eval context" — bare Python/urllib gets HTTP error 1010.
funnel_create()/step_create()/page_autosave() therefore build the exact REST step (method,
path, body, expected response shape) and, when a `session` kwarg names a live agent-browser
session, an `argv` to run it — but they never make a network call themselves, and calling
them WITHOUT a session (as this offline builder does) is 100% pure/local: no import of
browser_manager is even attempted. This is the SAME seam this repo already uses for GHL
funnel/page builds: 56-sales-page-assets/run_sales_page_assets.py's P9-HANDOFF phase does
not drive a browser either — it gates on a delegated `build_receipt.json` carrying real
`preview_urls` + a QC score (see `_build_receipt_gate` there). This module mirrors that
exact, already-established pattern: it builds the funnel/step/page-autosave REST steps with
ghl_rest_canvas's real functions (never reimplementing GHL REST), writes them as an ordered
execution plan (`working/sales-checkout/ghl_push_plan.json`) for an agent holding a live
agent-browser session to execute, then verifies the resulting
`working/sales-checkout/build_receipt.json` before calling the phase pushed. Absence of a
receipt is NOT a failure — it is "plan emitted, awaiting delegated execution" (exit 0); a
PRESENT but placeholder/fabricated receipt IS a failure (exit 4).

USAGE
    python3 scripts/sales_checkout_builder.py --run-dir <run_dir> [--skip-design] [--no-push]
    python3 scripts/sales_checkout_builder.py --selftest

    --run-dir     The governed pipeline run dir (reads working/copy/intake.json).
    --skip-design Reuse already-downloaded hero renders (working/sales-checkout/renders/)
                  without a fresh kie.ai run. Copy + HTML + plan + receipt-check only.
    --no-push     Skip the front-door-nonce requirement and the GHL push plan/receipt
                  steps entirely (offline smoke build: copy + design + HTML only, no
                  client GHL write, no push-plan artifact).
    --selftest    Deterministic offline self-test (no network, no kie.ai spend, no GHL
                  call of any kind — every ghl_rest_canvas call below is made WITHOUT a
                  session, which is pure/local by construction).

FRONT-DOOR NONCE (mirrors build_deck.py / workbook_builder.py / build_webinar_video.py)
    presentation-canonical-entry.sh mints OC_DECK_ENTRY_NONCE + the run-scoped 0600 file
    <run-dir>/working/checkpoints/.canonical-entry-nonce. A hand-rolled invocation that
    would spend kie.ai money or touch a client's GHL funnel is refused (exit 2,
    AF-CANONICAL-RENDER-BYPASS) unless --no-push. --no-push offline smoke builds are exempt
    (no client GHL write is possible on that path).

EXIT CODES
    0  — DEFERRED (flag absent -- nothing to do this run), or WAIVED (client declined with
         a recorded reason -- correctly gated out), or BUILT (copy+design+HTML+plan emitted,
         receipt not yet present -- awaiting delegated agent-browser execution), or PUSHED
         (a valid delegated receipt was found and verified)
    1  — kie.ai design/render failure
    2  — fatal configuration error (no API key, missing run-dir, refused nonce)
    3  — GATE BLOCKED: a bare "no" with no verbatim client reason, or an unrecognized
         WANT_SALES_CHECKOUT value (AF-UPSELL-WAIVER-MISSING / AF-UPSELL-VALUE-UNRECOGNIZED)
    4  — VERIFY FAILED: a present build_receipt.json is placeholder/fabricated (no real
         preview_urls, or no funnel_id), or an assembled artifact failed its content gate
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_BUILD_FAILED = 1
EXIT_USAGE = 2
EXIT_GATE_BLOCKED = 3
EXIT_VERIFY_FAILED = 4

# ---------------------------------------------------------------------------
# Waiver mechanic constants (mirrors presentation_job/waivers.py's own floor:
# `if len(quote) < 3: raise WaiverError(... "a waiver the agent wrote for itself
# is not a waiver")`) and upsell-questions.json's storeTarget field names.
# ---------------------------------------------------------------------------
MIN_WAIVER_QUOTE_CHARS = 3
WANT_FIELD = "WANT_SALES_CHECKOUT"
REASON_FIELD = "SALES_CHECKOUT_DECLINED_REASON"
AF_WAIVER_MISSING = "AF-UPSELL-WAIVER-MISSING"
AF_VALUE_UNRECOGNIZED = "AF-UPSELL-VALUE-UNRECOGNIZED"
AF_PROMPT_NO_CONTENT = "AF-SALES-PROMPT-NO-CONTENT"

# ---------------------------------------------------------------------------
# Design-prompt band (mirrors workbook_builder.py's Presentations rich-prompt gate:
# 9,000-18,000 stripped chars).
# ---------------------------------------------------------------------------
PROMPT_FLOOR = 9000
PROMPT_CEILING = 18000

ASPECT_RATIO = "16:9"
RESOLUTION = "2K"

# Front-door nonce (identical contract to workbook_builder.py / build_deck.py).
ENTRY_NONCE_REL = Path("working") / "checkpoints" / ".canonical-entry-nonce"

# Brand defaults when intake carries no palette (mirrors workbook_builder.py's fallback).
DEFAULT_PRIMARY = "#212748"
DEFAULT_SECONDARY = "#B38456"
DEFAULT_ACCENT = "#C49A70"
DEFAULT_BASE = "#F2E6D7"
DEFAULT_INK = "#1A1A1A"

# Placeholder hosts a delegated receipt's preview_urls must never resolve to (mirrors
# 56-sales-page-assets/run_sales_page_assets.py's PLACEHOLDER_HOSTS -- "a caller-authored
# preview proves no page was built").
PLACEHOLDER_HOSTS = (
    "example.com", "example.org", "example.net", "example.edu", "invalid",
    "localhost", "127.0.0.1", "0.0.0.0", "test.com", "changeme.com", "todo.com",
)

WIREFRAME_BAN_PHRASES = (
    "background only", "background-only", "no text", "wireframe", "blank template",
    "blank page background",
)


# ---------------------------------------------------------------------------
# Optional shared prompt-gate (degrade gracefully -- mirrors workbook_builder.py).
# ---------------------------------------------------------------------------
def _load_prompt_gate():
    try:
        import prompt_gate  # noqa: F401
        return prompt_gate
    except Exception:  # noqa: BLE001
        return None


prompt_gate = _load_prompt_gate()


# ---------------------------------------------------------------------------
# Sibling-module resolution (never a hardcoded operator path -- HOME/repo-relative,
# same discipline kie_generate.py's HIGH-3 fix and _import_prompt_gate use).
# ---------------------------------------------------------------------------
def _here() -> Path:
    return Path(__file__).resolve().parent


def _find_ghl_rest_canvas_dir() -> Optional[Path]:
    """Walk every ancestor of this file looking for the sibling Skill-6 tools dir
    that ships ghl_rest_canvas.py. Works identically inside this repo checkout/
    worktree and on a deployed client box, because both mirror the same
    <repo-root>/06-ghl-install-pages/tools layout -- no absolute path is ever
    assumed (mirrors kie_generate.py's HIGH-3 no-hardcoded-operator-path rule)."""
    for parent in _here().parents:
        cand = parent / "06-ghl-install-pages" / "tools"
        if (cand / "ghl_rest_canvas.py").is_file():
            return cand
    return None


def _import_ghl_rest_canvas():
    cand = _find_ghl_rest_canvas_dir()
    if cand is None:
        raise RuntimeError(
            "ghl_rest_canvas.py not found under any ancestor's 06-ghl-install-pages/tools -- "
            "cannot build the GHL push plan. This module refuses to reimplement GHL REST; "
            "it only reuses the real ghl_rest_canvas.py helpers."
        )
    if str(cand) not in sys.path:
        sys.path.insert(0, str(cand))
    import ghl_rest_canvas  # noqa: E402
    return ghl_rest_canvas


def _import_ghl_media():
    """The sibling department module (co-located with this script) used ONLY to host
    the kie-rendered hero PNG in the GHL media library before it can be referenced by
    a GHL-media-storage <img src> (ghl_rest_canvas's images-as-media-links invariant).
    Never used for the funnel/page push itself -- that is ghl_rest_canvas's job."""
    here = _here()
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import ghl_media  # noqa: E402
    return ghl_media


# ---------------------------------------------------------------------------
# intake.json helpers
# ---------------------------------------------------------------------------
def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return {}


def load_intake(run_dir: Path) -> dict:
    return _read_json(run_dir / "working" / "copy" / "intake.json")


def resolve_brief(intake: dict) -> Dict[str, Any]:
    brief = intake.get("deck_brief")
    return brief if isinstance(brief, dict) else {}


def _hex_color(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    v = value.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", v):
        return v
    m = re.fullmatch(r"([0-9a-f]{6})", v)
    if m:
        return "#" + m.group(1)
    return default


def _first_hex_from_design_brief(run_dir: Path) -> Optional[str]:
    """Best-effort fallback (mirrors workbook_builder.py's identically-named helper):
    when intake carries no BRAND_PRIMARY, pull the first 6-hex token from a design
    brief in this run dir rather than falling all the way back to the generic default."""
    brief_dir = run_dir / "working" / "research"
    if not brief_dir.is_dir():
        return None
    for f in sorted(brief_dir.glob("design-brief-*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hexes = re.findall(r"#[0-9a-fA-F]{6}\b", text)
        if hexes:
            return _hex_color(hexes[0], DEFAULT_PRIMARY)
    return None


def resolve_brand(run_dir: Path, intake: dict) -> Dict[str, str]:
    brief = resolve_brief(intake)
    primary = _hex_color(brief.get("BRAND_PRIMARY"), None) or _first_hex_from_design_brief(run_dir) or DEFAULT_PRIMARY
    return {
        "primary": primary,
        "secondary": DEFAULT_SECONDARY,
        "accent": DEFAULT_ACCENT,
        "base": DEFAULT_BASE,
        "ink": DEFAULT_INK,
    }


def resolve_deck_slug(run_dir: Path, intake: dict) -> str:
    slug = intake.get("deck_slug") or run_dir.name
    return str(slug).strip() or "presentation"


def resolve_client_name(run_dir: Path, intake: dict) -> str:
    brief = resolve_brief(intake)
    for key in ("OFFER_NAME",):
        v = brief.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for key in ("client_name", "company", "business_name", "name"):
        v = intake.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return resolve_deck_slug(run_dir, intake).replace("-", " ").title()


# ---------------------------------------------------------------------------
# THE GATE — resolve_sales_checkout_gate()
# ---------------------------------------------------------------------------
def resolve_sales_checkout_gate(intake: dict) -> Dict[str, Any]:
    """Resolve WANT_SALES_CHECKOUT against upsell-questions.json's waiver_field_mapping
    (U026). Returns {"decision": "defer"|"build"|"waived"|"fail_closed", "detail": str, ...}.

    Never conflates "absent" with "declined" -- silence is NOT consent (upsell-
    questions.json's own words, verbatim). A "no" ALWAYS requires a real, non-empty
    verbatim client reason at SALES_CHECKOUT_DECLINED_REASON or the gate fails closed
    (mirrors presentation_job/waivers.py's `len(quote) < 3` self-authored-waiver guard).
    """
    pre = intake.get("pre_presentation_capture")
    pre = pre if isinstance(pre, dict) else {}

    raw = pre.get(WANT_FIELD)
    if isinstance(raw, dict):
        raw = raw.get("value")
    if raw is None or not str(raw).strip():
        return {
            "decision": "defer",
            "detail": (
                f"pre_presentation_capture.{WANT_FIELD} is absent/blank -- this run's "
                "intake never asked/answered the upsell question. DEFERRING: an absent "
                "answer is NEVER treated as a decline (silence is not consent)."
            ),
            "want_raw": raw,
        }

    norm = str(raw).strip().lower()
    if norm == "yes":
        return {"decision": "build", "detail": "client answered yes.", "want_raw": raw}

    if norm != "no":
        return {
            "decision": "fail_closed",
            "detail": (
                f"{AF_VALUE_UNRECOGNIZED}: {WANT_FIELD}={raw!r} is neither 'yes' nor 'no' "
                "-- refusing to guess (mirrors intake_writer.py's UngroundedDeckTypeError "
                "fail-closed discipline: an unrecognized answer is never defaulted)."
            ),
            "want_raw": raw,
        }

    # norm == "no": a decline REQUIRES the client's own verbatim reason.
    reason_raw = pre.get(REASON_FIELD)
    if isinstance(reason_raw, dict):
        reason_raw = reason_raw.get("value")
    reason = str(reason_raw or "").strip()
    if len(reason) < MIN_WAIVER_QUOTE_CHARS:
        return {
            "decision": "fail_closed",
            "detail": (
                f"{AF_WAIVER_MISSING}: {WANT_FIELD}=no but {REASON_FIELD} is missing/blank "
                "-- a decline with no verbatim client reason is not a waiver "
                "(upsell-questions.json waiver_field_mapping.sales_checkout; "
                "'silence is NOT consent'). Refusing to silently skip the build."
            ),
            "want_raw": raw,
            "reason_raw": reason_raw,
        }

    return {
        "decision": "waived",
        "detail": "client declined with a recorded verbatim reason -- gated OUT (not a failure).",
        "want_raw": raw,
        "quote": reason,
    }


# ---------------------------------------------------------------------------
# COPY — deterministic, offline, template-driven from the run's own intake brief.
# No fabricated specifics: every field falls back to a generic, honest placeholder
# phrase (mirrors intake_writer.py's own `brief.get("AUDIENCE") or "the stated
# audience"` fallback idiom) rather than inventing a client claim.
# ---------------------------------------------------------------------------
def build_sales_copy(brief: Dict[str, Any], client_name: str) -> str:
    offer = brief.get("OFFER_NAME") or "this offer"
    promise = brief.get("TRANSFORMATION_PROMISE") or "a clear, stated transformation"
    audience = brief.get("AUDIENCE") or "the stated audience"
    cta = brief.get("CTA_ACTION") or "Get Started"
    price = brief.get("FINAL_PRICE") or ""
    objection = brief.get("PRIMARY_OBJECTION") or "the audience's most common hesitation"
    proof = brief.get("PROOF_ASSETS") or "the client's real results and proof assets"
    hook = brief.get("HOOK_SEED") or promise
    tone = brief.get("TONE") or "confident, direct"
    offer_line = offer + (f" — {price}" if price else "")
    return "\n".join([
        f"# {client_name} — Sales Page Copy",
        "",
        "## Hero Headline",
        str(hook),
        "",
        "## Subheadline",
        f"{offer} for {audience}.",
        "",
        "## The Promise",
        str(promise),
        "",
        "## Who This Is For",
        str(audience),
        "",
        "## Objection Handled",
        str(objection),
        "",
        "## Proof",
        str(proof),
        "",
        "## Offer",
        offer_line,
        "",
        "## Call To Action",
        str(cta),
        "",
        f"_Tone: {tone}_",
    ]) + "\n"


def build_checkout_copy(brief: Dict[str, Any], client_name: str) -> str:
    offer = brief.get("OFFER_NAME") or "this offer"
    price = brief.get("FINAL_PRICE") or ""
    price_mode = brief.get("PRICE_MODE") or ""
    cta = brief.get("CTA_ACTION") or "Complete My Order"
    reassurance = brief.get("PRIMARY_OBJECTION") or "Secure checkout. Your information is protected."
    order_line = offer
    if price and price_mode:
        order_line += f" — {price} ({price_mode})"
    elif price:
        order_line += f" — {price}"
    return "\n".join([
        f"# {client_name} — Checkout Page Copy",
        "",
        "## Order Summary",
        order_line,
        "",
        "## Reassurance",
        str(reassurance),
        "",
        "## Call To Action",
        str(cta),
    ]) + "\n"


def _content_fields_for_page(page_role: str, brief: Dict[str, Any], client_name: str) -> Dict[str, str]:
    """The verbatim content strings a design prompt must bake into the image --
    mirrors workbook_builder.py's _page_content_strings/content-in-image discipline."""
    if page_role == "sales":
        return {
            "headline": str(brief.get("HOOK_SEED") or brief.get("TRANSFORMATION_PROMISE") or f"{client_name}"),
            "subhead": f"{brief.get('OFFER_NAME') or 'This offer'} for {brief.get('AUDIENCE') or 'you'}.",
            "cta": str(brief.get("CTA_ACTION") or "Get Started"),
        }
    return {
        "headline": "Complete Your Order",
        "subhead": str(brief.get("OFFER_NAME") or "this offer"),
        "cta": str(brief.get("CTA_ACTION") or "Complete My Order"),
    }


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _page_content_strings(fields: Dict[str, str]) -> List[str]:
    return [v.strip() for v in fields.values() if isinstance(v, str) and len(v.strip()) >= 3]


def assert_content_in_prompt(page_id: str, fields: Dict[str, str], prompt: str) -> None:
    """AF-SALES-PROMPT-NO-CONTENT -- fail-closed PRE-SUBMIT content gate. Mirrors
    workbook_builder.py's _assert_content_in_prompt exactly: a wireframe/background-only
    directive, or a page carrying zero content strings, or content not baked verbatim,
    is refused before any paid kie.ai render."""
    low = prompt.lower()
    for phrase in WIREFRAME_BAN_PHRASES:
        if phrase in low:
            raise RuntimeError(
                f"{page_id}: {AF_PROMPT_NO_CONTENT} -- wireframe directive {phrase!r} "
                "present in the prompt; refusing to submit a content-empty page."
            )
    strings = _page_content_strings(fields)
    if not strings:
        raise RuntimeError(
            f"{page_id}: {AF_PROMPT_NO_CONTENT} -- page carries ZERO content strings; "
            "a background-only prompt is refused before any paid render."
        )
    norm_prompt = _norm_ws(prompt)
    missing = [s for s in strings if _norm_ws(s) not in norm_prompt]
    if missing:
        raise RuntimeError(
            f"{page_id}: {AF_PROMPT_NO_CONTENT} -- {len(missing)} content string(s) not "
            f"baked verbatim into the prompt: {missing[:3]}"
        )


def _assert_prompt_band(prompt: str, page_id: str) -> None:
    stripped = prompt.strip()
    n = len(stripped)
    if n < PROMPT_FLOOR:
        raise RuntimeError(
            f"{page_id}: prompt is {n} chars, UNDER the {PROMPT_FLOOR}-char floor."
        )
    if n > PROMPT_CEILING:
        raise RuntimeError(
            f"{page_id}: prompt is {n} chars, OVER the {PROMPT_CEILING}-char ceiling."
        )
    if prompt_gate is not None:
        try:
            prompt_gate.verify_prompt_minimal(prompt, slide_id=page_id)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"{page_id}: shared prompt gate rejected the design prompt: {exc}")


def build_design_prompt(*, page_role: str, brand: Dict[str, str], client_name: str,
                        fields: Dict[str, str], page_index: int, page_count_total: int) -> str:
    """Compose a content-in-image sales/checkout hero design prompt (9,000-18,000
    stripped chars), templating workbook_builder.py's proven content-in-image
    technique for a marketing hero rather than a workbook page."""
    prim, sec, acc = brand["primary"], brand["secondary"], brand["accent"]
    base, ink = brand["base"], brand["ink"]
    headline = fields.get("headline", "")
    subhead = fields.get("subhead", "")
    cta = fields.get("cta", "")
    role_label = "SALES PAGE HERO" if page_role == "sales" else "CHECKOUT PAGE"
    purpose = (
        "convert a cold visitor into a buyer by proving the promise and removing the "
        "one objection standing between them and the offer"
        if page_role == "sales" else
        "reassure a warm buyer already committed to purchase, remove friction, and "
        "get the order completed with zero doubt"
    )
    prompt = f"""[ARCHETYPE ZHC-{role_label.replace(' ', '-')}]
DESIGN A SINGLE FULL-BLEED WEB PAGE HERO DESIGN, LANDSCAPE, {ASPECT_RATIO} ASPECT, {RESOLUTION}.
This is a DESIGNED, CONTENT-RICH {role_label.lower()} design for {client_name}. Render the
page's REAL content (headline, subheadline, call-to-action label) baked into the image by
the text-to-image engine, in the brand system below. Every quoted string must be rendered
VERBATIM, letter-for-letter.

=== PAGE ROLE & WHAT THIS PAGE IS FOR ===
This page is: {role_label}. Its job is to {purpose}. The visitor reads top-to-bottom:
headline, subheadline, supporting proof band, then the call-to-action. The page must stand
alone as a finished, premium marketing surface, not a placeholder shell, and must read
clearly at a glance on both desktop and mobile crops.

=== BRAND LOCKUP ===
Client: {client_name}. Grade: premium, confident, conversion-focused, editorial.
Brand palette (use these EXACT hex values, no substitutions):
  Primary {prim} — header band, CTA button fill, section rules.
  Secondary {sec} — accent bands, supporting text highlights.
  Accent {acc} — one geometric motif + the emphasis color for key words.
  Base {base} — page background.
  Ink {ink} — body text ink.
Typography character: a geometric editorial sans, weight ladder BLACK hero (48-64pt),
ExtraBold subhead (22-28pt), Bold CTA label (18-22pt), Medium supporting copy (13-15pt).

=== PAGE CONTENT (the real content — bake verbatim) ===
HEADLINE (render large, upper content band, {ink} on {base} or white on {prim} band):
  {headline!r}
SUBHEADLINE (directly beneath the headline, ExtraBold):
  {subhead!r}
CALL-TO-ACTION BUTTON (a solid {prim}-filled pill/rectangle button, white label text,
centered in the lower third):
  {cta!r}

=== VERBATIM + SPELLING-LOCK ===
Render EVERY quoted string above letter-for-letter, exactly as written, spelled exactly,
no paraphrasing, no substitution, no reordering, no typo, no garble, no truncation, no
ellipsis unless it is in the source string. The quoted strings above are the ONLY text on
this page beyond the {client_name} wordmark. Text must read exactly as quoted — this is
the spelling-lock for every baked string above.

=== LAYOUT GRID (fixed, landscape {ASPECT_RATIO}) ===
HEADER BAND (top 0-14%): solid {prim} band carrying the {client_name} wordmark, small,
top-left, in white; a thin {acc} rule at the band's bottom edge.
HERO BAND (14-62%): on {base}. The headline sits upper-left or centered (whichever reads
cleaner at this aspect), the subheadline directly beneath it in the {sec}-accented weight.
Generous negative space around both; nothing else competes with them in this band.
PROOF/SUPPORT BAND (62-82%): a quiet horizontal strip carrying a single supporting visual
motif (an abstract geometric shape system in {acc}, never a literal photograph of people —
see the DO-NOT BLOCK anatomical-artifacts rule below) that reinforces credibility without
adding any additional quoted text beyond what is specified above.
CTA BAND (82-100%): the solid {prim} call-to-action button, centered, with the CTA label in
white, large enough to read at a glance; a hairline {sec} rule above the band.
Safe margins 0.5in-equivalent on all sides; nothing touches the edges.

=== CONTENT ZONE PLACEMENT (fixed, page {page_index} of {page_count_total} in this set) ===
On a strict horizontal-thirds grid: the HEADER band anchors identity, the HERO band carries
the headline+subheadline pair as the unmistakable focal point (largest type on the page,
highest contrast against {base}), the PROOF band is quiet and supportive (never louder than
the hero type), and the CTA band closes with one unmissable button. The bands and their
relative heights are IDENTICAL across the set (sales + checkout) so the two pages read as
one designed system with the same brand lockup, only the headline/subhead/CTA content and
supporting-band emphasis differ per page role. Each band's boundary is a hard edge; no
element from one band is permitted to bleed, overlap, or cast a shadow into the next band,
so a downstream crop tool can safely lift any single band without cutting live content.

=== MOTIF & TEXTURE ===
One quiet {acc} geometric motif system anchors the PROOF band: a repeating thin-line shape
(concentric arcs, a single large circle cropped at the frame edge, or a subtle diagonal
hairline grid), rendered at low opacity so it never competes with the type above or the CTA
button below. The motif never touches an answer/CTA zone, never sits behind the headline,
and never introduces additional readable text of its own — it is texture, not content. Keep
the motif restrained: a premium page reads as confident and uncluttered, not busy.

=== RESPONSIVE / MOBILE-CROP DISCIPLINE ===
Although this render is a single fixed {ASPECT_RATIO} frame, design every band so a naive
center-crop to a taller mobile ratio still keeps the headline, subheadline, and CTA button
fully legible and un-cropped: keep the hero type and the CTA button horizontally centered
within the middle 70% of the frame width, and keep all four content elements (headline,
subheadline, proof motif, CTA button) vertically stacked in that same reading order with no
element depending on being seen alongside another to make sense on its own.

=== ACCESSIBILITY / CONTRAST ===
Every quoted string must clear a strong contrast ratio against its immediate background —
{ink} or white text only ever sits on a fill that keeps it easily readable at a glance, never
a mid-tone fill that washes the letterforms out. The CTA button's white label on the {prim}
fill is the single highest-contrast pairing on the page; nothing else may compete with it
for visual weight. Every quoted string stays at or above the body-copy floor named in the
TYPE SPEC below, always set in a color that clears its background with margin so nothing
blurs together at a glance.

=== DO-NOT BLOCK (the 8 defect classes, named — for a CONTENT-BEARING page) ===
1. GARBLED/MISSPELLED TEXT — misspell, garble, phonetic drift, or truncation of any quoted
   string; render every quoted string letter-for-letter, exactly as written. If a word is
   hard to set, do not omit it and do not swap a synonym — set the exact string.
2. LOGO MUTATION — do not fabricate a logo; render only the {client_name} wordmark as a
   clean typographic lockup (no invented icon/mark) unless a real logo is later composited.
3. PLACEHOLDER/BRACKET TOKENS — no bracketed token, no square brackets around the quoted
   content, no "owner to confirm", no TBD, no "insert here", no build note, no "to supply",
   no pending marker anywhere on the page.
4. IMAGE NARRATION/PRESENTER/META — no narrator line, no stage direction, no "this is a
   sales page" meta text, no design-brief fragment leaking onto the canvas.
5. ANATOMICAL ARTIFACTS — no people are specified for this composition, so none may appear:
   no people, no fused hands, no fingers, no malformed anatomy, no distorted facial
   features, no mismatched eyes, no asymmetric eyes, no distorted teeth.
6. BACKGROUND COMPETING WITH TEXT — no busy or cluttered background, no pattern or texture
   under the text zones; keep generous negative space and high contrast on every quoted
   line; add a soft scrim behind text where needed so every letter reads clearly.
7. DEMOGRAPHIC/SKIN-TONE FIDELITY — no demographic default, no skin-tone drift (this
   composition has no people; the rule carries forward as a universal baseline).
8. CARRIED-FORWARD UNIVERSAL BASELINE — no watermark over content, no emoji, no clipart,
   no default font (Calibri/Arial/Times New Roman), no em dash, no system UI artifact, no
   pure-black fill. All text in the geometric editorial sans family at the sizes above.

=== COMPOSITION / TYPE SPEC ===
Horizontal-thirds grid; the headline is the hero; reading order = header wordmark ->
headline -> subheadline -> proof band -> CTA button. Brand hex: {prim}, {sec}, {acc},
{base}, {ink}. Headline 48-64pt BLACK, subheadline 22-28pt ExtraBold, CTA label 18-22pt
Bold, supporting body copy never below 13pt Medium. 8th-row readability: the headline and
CTA button must still read when the page is shrunk to 25%. The CTA button must be the
single highest-contrast element on the page, and must remain a single unbroken shape (no
text or motif is ever permitted to overlap its fill).

=== REFERENCE MOOD ===
Think of the finished page the way a premium SaaS or coaching-offer landing page reads at a
glance: confident whitespace, one obvious next action, a brand system that feels considered
rather than templated. The mood is warm-professional, never corporate-cold and never
carnival-loud — the palette above (never substituted) carries that warmth on its own; no
additional decorative color is introduced.

=== QUALITY ===
Crisp {RESOLUTION} edges, flat clean editorial-conversion aesthetic, professional {role_label.lower()}
design, high information density of DESIGN (brand + hierarchy), soft even tone, uniform
lighting, no competing visual firsts, no crop, no letterbox. The page reads as a premium,
fully designed, content-complete marketing surface from the first glance — every band
finished, every zone resolved, nothing left for a later pass to fill in.

=== DETERMINISTIC VARIANT (page {page_index} of {page_count_total}) ===
This is the {role_label.lower()} of a two-page set (sales + checkout) sharing one brand
lockup: identical header band, identical palette, identical typography ladder, identical
band structure, identical motif treatment. Only the headline/subheadline/CTA copy and the
proof-band emphasis differ between the two pages, so the set reads as one designed system
end to end — the same visitor recognizes the checkout page as a continuation of the sales
page they just left, never a different site.
"""
    return prompt


# ---------------------------------------------------------------------------
# HTML — body-level fragment (ghl_rest_canvas.html_fragment-compatible: no
# <!DOCTYPE>/<html>/<head>/<body> wrapper). Inline <style> is fine inside a bare
# fragment (lint_ghl_fragment explicitly allows it, confirmed render-surviving).
# ---------------------------------------------------------------------------
def build_page_html(*, page_role: str, brand: Dict[str, str], client_name: str,
                    fields: Dict[str, str], hero_image_src: Optional[str],
                    marker: str) -> str:
    prim, sec, acc, base, ink = (
        brand["primary"], brand["secondary"], brand["accent"], brand["base"], brand["ink"]
    )
    headline = fields.get("headline", "")
    subhead = fields.get("subhead", "")
    cta = fields.get("cta", "")
    hero_img_tag = (
        f'<img src="{hero_image_src}" alt="{client_name} {page_role} hero" '
        f'style="width:100%;max-width:100%;display:block;border-radius:12px;margin:0 0 24px;">'
        if hero_image_src else
        '<!-- hero image not yet hosted in GHL media (offline/no-push build) -->'
    )
    body_extra = ""
    if page_role == "sales":
        body_extra = f"""
    <div class="proof">
      <p>{fields.get('proof', '')}</p>
    </div>"""
    else:
        body_extra = f"""
    <div class="order-summary">
      <p>{fields.get('order_line', '')}</p>
      <p class="reassurance">{fields.get('reassurance', '')}</p>
    </div>"""
    return f"""<!-- ZHC-SALES-CHECKOUT-BUILDER marker={marker} page_role={page_role} -->
<style>
  .zhc-{page_role}-page {{ font-family: 'Montserrat', Arial, sans-serif; background:{base}; color:{ink}; padding:32px 24px; }}
  .zhc-{page_role}-page h1 {{ color:{ink}; font-size:2.4em; font-weight:800; margin:0 0 12px; }}
  .zhc-{page_role}-page h2 {{ color:{sec}; font-size:1.3em; font-weight:600; margin:0 0 24px; }}
  .zhc-{page_role}-page .cta-button {{ display:inline-block; background:{prim}; color:#fff; font-weight:700; padding:16px 32px; border-radius:8px; text-decoration:none; font-size:1.1em; }}
  .zhc-{page_role}-page .proof, .zhc-{page_role}-page .order-summary {{ background:#fff; border:1px solid {sec}; border-radius:10px; padding:18px; margin:24px 0; }}
  .zhc-{page_role}-page .reassurance {{ color:{sec}; font-size:0.95em; }}
</style>
<div class="zhc-{page_role}-page">
  {hero_img_tag}
  <h1>{headline}</h1>
  <h2>{subhead}</h2>{body_extra}
  <a class="cta-button" href="#">{cta}</a>
</div>
"""


def _html_content_strings_present(html: str, fields: Dict[str, str]) -> List[str]:
    """Offline verification twin of workbook_builder.py's OCR content gate: HTML is
    text, not a rendered image, so a plain substring check IS the content proof (no
    OCR needed). Returns the list of missing strings (empty == all present)."""
    norm_html = _norm_ws(re.sub(r"<[^>]+>", " ", html))
    missing = []
    for s in _page_content_strings(fields):
        if _norm_ws(s) not in norm_html:
            missing.append(s)
    return missing


# ---------------------------------------------------------------------------
# kie.ai design — reuse kie_generate.py verbatim (subprocess), never a new
# implementation of the KIE call (task rule: reuse the canonical helper).
# ---------------------------------------------------------------------------
def run_kie_generate(prompts: List[Dict[str, Any]], renders_dir: Path) -> Tuple[bool, str]:
    kie_script = _here() / "kie_generate.py"
    if not kie_script.is_file():
        return False, f"kie_generate.py not found beside this script at {kie_script}"
    renders_dir.mkdir(parents=True, exist_ok=True)
    prompts_path = renders_dir.parent / "sales_checkout_prompts.json"
    prompts_path.write_text(json.dumps(prompts, indent=2), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(kie_script), str(prompts_path), str(renders_dir)],
        capture_output=True, text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        return False, f"kie_generate.py exited {proc.returncode}"
    return True, "kie_generate.py: all slides downloaded"


# ---------------------------------------------------------------------------
# GHL push plan — real ghl_rest_canvas.py functions, called WITHOUT a `session`
# kwarg so the calls are pure/local (no agent-browser, no network, no
# browser_manager import at all -- see funnel_create/step_create/page_autosave's
# own source: the `if session:` branch is the ONLY place that touches a browser).
# ---------------------------------------------------------------------------
def build_ghl_push_plan(*, location_id: str, funnel_name: str, deck_slug: str,
                        sales_html: str, checkout_html: str, brand: Dict[str, str]) -> Dict[str, Any]:
    rc = _import_ghl_rest_canvas()

    sales_slug = f"{deck_slug}-sales"
    checkout_slug = f"{deck_slug}-checkout"

    # Pure, local step descriptors (no session -> no browser call of any kind).
    funnel_step = rc.funnel_create(location_id, funnel_name, funnel_type="funnel")

    # The two page_data blobs are built and internally shape-validated NOW
    # (new_page_blob() raises AssertionError on any renderability defect before
    # this plan is ever handed to an executing agent) -- never reimplementing
    # ghl_rest_canvas's own validated blob assembly.
    sales_blob = rc.new_page_blob(
        sales_html, surface="funnel",
        primary_color=brand.get("primary"), secondary_color=brand.get("secondary"),
    )
    checkout_blob = rc.new_page_blob(
        checkout_html, surface="funnel",
        primary_color=brand.get("primary"), secondary_color=brand.get("secondary"),
    )

    return {
        "note": (
            "Delegated GHL push plan. ghl_rest_canvas.py's /funnels/* routes are "
            "Cloudflare-WAF-gated and MUST run inside a live agent-browser eval "
            "context (bare Python gets HTTP error 1010) -- this builder cannot drive "
            "a browser itself. An agent holding a seeded, activated, GHL-origin-"
            "navigated agent-browser session executes the `sequence` below IN ORDER, "
            "using the REAL ghl_rest_canvas.py functions named (never reimplemented), "
            "then writes working/sales-checkout/build_receipt.json with the real "
            "resulting preview_urls + funnel_id + a QC score >= 8.5 (mirrors "
            "56-sales-page-assets/run_sales_page_assets.py's P9-HANDOFF build_receipt "
            "contract). Re-running this builder after that receipt lands verifies it "
            "and reports PUSHED."
        ),
        "location_id": location_id,
        "funnel_name": funnel_name,
        "sequence": [
            {
                "step": 1,
                "call": "ghl_rest_canvas.funnel_create",
                "args": {"location_id": location_id, "name": funnel_name, "funnel_type": "funnel"},
                "precomputed_step": funnel_step,
                "then": "run the eval; parse response body.id -> FUNNEL_ID",
            },
            {
                "step": 2,
                "call": "ghl_rest_canvas.step_create",
                "args": {"funnel_id": "FUNNEL_ID", "name": f"{funnel_name} — Sales", "slug": sales_slug},
                "then": "run the eval; created_page_id(response) -> SALES_PAGE_ID (new_page_version=1)",
            },
            {
                "step": 3,
                "call": "ghl_rest_canvas.page_autosave",
                "args": {"page_id": "SALES_PAGE_ID", "funnel_id": "FUNNEL_ID", "page_version": 1,
                        "page_data": sales_blob},
                "then": "run the eval; expect 201; live pointer unchanged (draft)",
            },
            {
                "step": 4,
                "call": "ghl_rest_canvas.step_create",
                "args": {"funnel_id": "FUNNEL_ID", "name": f"{funnel_name} — Checkout", "slug": checkout_slug},
                "then": "run the eval; created_page_id(response) -> CHECKOUT_PAGE_ID (new_page_version=1)",
            },
            {
                "step": 5,
                "call": "ghl_rest_canvas.page_autosave",
                "args": {"page_id": "CHECKOUT_PAGE_ID", "funnel_id": "FUNNEL_ID", "page_version": 1,
                        "page_data": checkout_blob},
                "then": "run the eval; expect 201; live pointer unchanged (draft)",
            },
        ],
        "page_data": {"sales": sales_blob, "checkout": checkout_blob},
        "slugs": {"sales": sales_slug, "checkout": checkout_slug},
    }


def _url_host(url: Any) -> str:
    from urllib.parse import urlparse
    if not isinstance(url, str):
        return ""
    try:
        return (urlparse(url.strip()).hostname or "").lower()
    except (ValueError, TypeError):
        return ""


def _real_url(url: Any) -> Tuple[bool, str]:
    """Mirrors 56-sales-page-assets/run_sales_page_assets.py's _real_url exactly:
    an http(s) URL whose host is not a placeholder host or a subdomain of one."""
    if not isinstance(url, str) or not url.strip().lower().startswith(("http://", "https://")):
        return False, f"{url!r} is not an http(s) URL"
    host = _url_host(url)
    if not host:
        return False, f"{url!r} has no host"
    if any(host == ph or host.endswith("." + ph) for ph in PLACEHOLDER_HOSTS):
        return False, f"{url!r} resolves to placeholder host {host!r}"
    return True, host


def verify_push_receipt(run_dir: Path) -> Tuple[Optional[bool], str, dict]:
    """Returns (status, detail, data). status: True = verified real push, False =
    present-but-fabricated (a genuine failure), None = absent (not yet executed,
    NOT a failure -- mirrors the 56-sales-page-assets P9 build_receipt contract)."""
    receipt_path = run_dir / "working" / "sales-checkout" / "build_receipt.json"
    if not receipt_path.is_file():
        return None, "no build_receipt.json -- push plan emitted, awaiting a delegated agent-browser run", {}
    try:
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"build_receipt.json unreadable: {exc}", {}
    if not isinstance(data, dict):
        return False, "build_receipt.json is not a JSON object", {}
    urls = data.get("preview_urls")
    if not (isinstance(urls, list) and [u for u in urls if str(u).strip()]):
        return False, "build_receipt.json carries no non-empty preview_urls", data
    bad = []
    for u in urls:
        ok, reason = _real_url(u)
        if not ok:
            bad.append(reason)
    if bad:
        return False, f"{len(bad)} preview URL(s) are not real: {bad[:2]}", data
    funnel_id = data.get("funnel_id")
    if not funnel_id or not str(funnel_id).strip():
        return False, "build_receipt.json carries no funnel_id", data
    return True, f"receipt verified ({len(urls)} real preview url(s), funnel_id={funnel_id})", data


# ---------------------------------------------------------------------------
# Front-door nonce (identical contract to workbook_builder.py / build_deck.py)
# ---------------------------------------------------------------------------
def _verify_entry_nonce(run_dir: Path) -> bool:
    import hmac
    env_nonce = (os.environ.get("OC_DECK_ENTRY_NONCE") or "").strip()
    if len(env_nonce) < 16:
        return False
    nf = run_dir / ENTRY_NONCE_REL
    try:
        file_nonce = nf.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return hmac.compare_digest(env_nonce, file_nonce)


# ---------------------------------------------------------------------------
# Ledger (mirrors workbook_builder.py's _record_ledger -- merged, never clobbered)
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_ledger(run_dir: Path, record: dict) -> None:
    ledger = run_dir / "working" / "checkpoints" / "sales_checkout.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(ledger.read_text()) if ledger.exists() else {}
    except Exception:  # noqa: BLE001
        existing = {}
    existing.update(record)
    ledger.write_text(json.dumps(existing, indent=2))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build the sales page + checkout page (kie.ai design -> copy -> "
                    "HTML -> delegated GHL funnel push), gated on WANT_SALES_CHECKOUT."
    )
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--skip-design", action="store_true",
                    help="reuse working/sales-checkout/renders/ PNGs; skip a fresh kie.ai run")
    ap.add_argument("--no-push", action="store_true",
                    help="offline smoke build: copy+design+HTML only, no nonce required, "
                         "no GHL push plan/receipt steps")
    ap.add_argument("--selftest", action="store_true", help="offline deterministic self-test")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.run_dir:
        ap.error("--run-dir is required (or --selftest)")
    run_dir = Path(args.run_dir).resolve()

    intake = load_intake(run_dir)

    # --- THE GATE ---
    gate = resolve_sales_checkout_gate(intake)
    print(f"\n=== WANT_SALES_CHECKOUT gate: {gate['decision'].upper()} ===")
    print(gate["detail"])
    if gate["decision"] == "defer":
        _record_ledger(run_dir, {"status": "deferred", "gate": gate, "checked_at": _now_iso()})
        return EXIT_OK
    if gate["decision"] == "fail_closed":
        _record_ledger(run_dir, {"status": "fail_closed", "gate": gate, "checked_at": _now_iso()})
        print(f"FATAL: {gate['detail']}", file=sys.stderr)
        return EXIT_GATE_BLOCKED
    if gate["decision"] == "waived":
        _record_ledger(run_dir, {"status": "waived", "gate": gate, "checked_at": _now_iso()})
        print(f"Waived with quote: {gate['quote']!r} -- nothing to build.")
        return EXIT_OK

    # decision == "build" from here down.
    if not args.no_push:
        if not _verify_entry_nonce(run_dir):
            print(
                "FATAL [AF-CANONICAL-RENDER-BYPASS]: sales_checkout_builder.py must run "
                "via presentation-canonical-entry.sh, which mints the per-run front-door "
                "nonce. Direct invocation is refused (a hand-rolled build cannot spend "
                "kie.ai money or touch a client's GHL funnel). Use --no-push ONLY for an "
                "operator offline smoke build (no client GHL write).",
                file=sys.stderr,
            )
            return EXIT_USAGE

    brand = resolve_brand(run_dir, intake)
    deck_slug = resolve_deck_slug(run_dir, intake)
    client_name = resolve_client_name(run_dir, intake)
    brief = resolve_brief(intake)

    sc_dir = run_dir / "working" / "sales-checkout"
    copy_dir = sc_dir / "copy"
    renders_dir = sc_dir / "renders"
    html_dir = sc_dir / "html"
    for d in (copy_dir, renders_dir, html_dir):
        d.mkdir(parents=True, exist_ok=True)

    # --- COPY ---
    sales_copy = build_sales_copy(brief, client_name)
    checkout_copy = build_checkout_copy(brief, client_name)
    (copy_dir / "sales.md").write_text(sales_copy, encoding="utf-8")
    (copy_dir / "checkout.md").write_text(checkout_copy, encoding="utf-8")
    print(f"\n=== Copy written -> {copy_dir}/{{sales,checkout}}.md ===")

    # --- DESIGN (kie.ai, unless --skip-design) ---
    sales_fields = _content_fields_for_page("sales", brief, client_name)
    checkout_fields = _content_fields_for_page("checkout", brief, client_name)

    sales_prompt = build_design_prompt(page_role="sales", brand=brand, client_name=client_name,
                                       fields=sales_fields, page_index=1, page_count_total=2)
    checkout_prompt = build_design_prompt(page_role="checkout", brand=brand, client_name=client_name,
                                          fields=checkout_fields, page_index=2, page_count_total=2)
    assert_content_in_prompt("sales-hero", sales_fields, sales_prompt)
    assert_content_in_prompt("checkout-hero", checkout_fields, checkout_prompt)
    _assert_prompt_band(sales_prompt, "sales-hero")
    _assert_prompt_band(checkout_prompt, "checkout-hero")

    sales_png = renders_dir / "sales-hero.png"
    checkout_png = renders_dir / "checkout-hero.png"
    if args.skip_design:
        missing = [p for p in (sales_png, checkout_png) if not p.exists()]
        if missing:
            print(f"FATAL: --skip-design but missing render(s): {missing}", file=sys.stderr)
            return EXIT_USAGE
    else:
        prompts = [
            {"slide": "sales-hero", "prompt": sales_prompt, "mode": "t2i",
             "aspect_ratio": ASPECT_RATIO, "resolution": RESOLUTION},
            {"slide": "checkout-hero", "prompt": checkout_prompt, "mode": "t2i",
             "aspect_ratio": ASPECT_RATIO, "resolution": RESOLUTION},
        ]
        ok, detail = run_kie_generate(prompts, renders_dir)
        print(f"\n=== kie.ai design: {detail} ===")
        if not ok:
            _record_ledger(run_dir, {"status": "design_failed", "detail": detail, "built_at": _now_iso()})
            return EXIT_BUILD_FAILED

    # --- HOST the hero renders in GHL media (only when we intend to push) ---
    sales_img_src = None
    checkout_img_src = None
    if not args.no_push:
        try:
            ghl_media = _import_ghl_media()
            pit = ghl_media.resolve_location_pit()
            location_id = ghl_media.resolve_location_id()
            up_sales = ghl_media.upload_media(str(sales_png), location_id, sales_png.name, pit,
                                              require_png=False, run_dir=run_dir)
            up_checkout = ghl_media.upload_media(str(checkout_png), location_id, checkout_png.name, pit,
                                                 require_png=False, run_dir=run_dir)
            sales_img_src = up_sales["url"]
            checkout_img_src = up_checkout["url"]
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: hero image GHL hosting failed ({exc}); HTML will be built "
                  "without a hosted hero image and the push plan step will fail its own "
                  "images-as-media-links gate until re-run.", file=sys.stderr)

    # --- HTML ---
    marker = f"ZHC-SC-{deck_slug}"
    sales_fields_html = dict(sales_fields, proof=brief.get("PROOF_ASSETS") or "")
    checkout_fields_html = dict(
        checkout_fields,
        order_line=(brief.get("OFFER_NAME") or "this offer")
        + (f" — {brief.get('FINAL_PRICE')}" if brief.get("FINAL_PRICE") else ""),
        reassurance=brief.get("PRIMARY_OBJECTION") or "Secure checkout. Your information is protected.",
    )
    sales_html = build_page_html(page_role="sales", brand=brand, client_name=client_name,
                                 fields=sales_fields_html, hero_image_src=sales_img_src, marker=marker)
    checkout_html = build_page_html(page_role="checkout", brand=brand, client_name=client_name,
                                    fields=checkout_fields_html, hero_image_src=checkout_img_src, marker=marker)
    (html_dir / "sales.html").write_text(sales_html, encoding="utf-8")
    (html_dir / "checkout.html").write_text(checkout_html, encoding="utf-8")
    print(f"\n=== HTML written -> {html_dir}/{{sales,checkout}}.html ===")

    missing_sales = _html_content_strings_present(sales_html, sales_fields)
    missing_checkout = _html_content_strings_present(checkout_html, checkout_fields)
    if missing_sales or missing_checkout:
        print(f"FATAL: content strings missing from assembled HTML -- sales:{missing_sales} "
              f"checkout:{missing_checkout}", file=sys.stderr)
        _record_ledger(run_dir, {"status": "html_content_gate_failed", "built_at": _now_iso()})
        return EXIT_VERIFY_FAILED

    record: Dict[str, Any] = {
        "deck_slug": deck_slug,
        "gate": gate,
        "sales_copy": str(copy_dir / "sales.md"),
        "checkout_copy": str(copy_dir / "checkout.md"),
        "sales_render": str(sales_png),
        "checkout_render": str(checkout_png),
        "sales_html": str(html_dir / "sales.html"),
        "checkout_html": str(html_dir / "checkout.html"),
        "built_at": _now_iso(),
    }

    if args.no_push:
        record["status"] = "built_offline_no_push"
        _record_ledger(run_dir, record)
        print("\nSALES/CHECKOUT BUILD (offline, --no-push): DONE")
        return EXIT_OK

    # --- GHL PUSH PLAN + delegated receipt check ---
    try:
        ghl_media = _import_ghl_media()
        location_id = ghl_media.resolve_location_id()
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: could not resolve GHL location id for the push plan: {exc}", file=sys.stderr)
        record["status"] = "push_plan_failed"
        record["error"] = str(exc)
        _record_ledger(run_dir, record)
        return EXIT_USAGE

    try:
        plan = build_ghl_push_plan(
            location_id=location_id, funnel_name=f"{client_name} — Sales/Checkout",
            deck_slug=deck_slug, sales_html=sales_html, checkout_html=checkout_html, brand=brand,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: GHL push plan construction failed: {exc}", file=sys.stderr)
        record["status"] = "push_plan_failed"
        record["error"] = str(exc)
        _record_ledger(run_dir, record)
        return EXIT_VERIFY_FAILED

    plan_path = sc_dir / "ghl_push_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"\n=== GHL push plan written -> {plan_path} ===")
    print("Execute the plan's `sequence` inside a live agent-browser session, write "
          "working/sales-checkout/build_receipt.json, then re-run this builder to verify.")

    status, detail, receipt_data = verify_push_receipt(run_dir)
    print(f"\n=== push receipt: {detail} ===")
    record["push_plan"] = str(plan_path)
    if status is True:
        record["status"] = "built+verified+pushed"
        record["receipt"] = receipt_data
        _record_ledger(run_dir, record)
        print("\nSALES/CHECKOUT BUILD: PUSHED")
        return EXIT_OK
    if status is False:
        record["status"] = "receipt_invalid"
        record["receipt_error"] = detail
        _record_ledger(run_dir, record)
        print(f"FATAL [AF-UPSELL-RECEIPT-INVALID]: {detail}", file=sys.stderr)
        return EXIT_VERIFY_FAILED

    record["status"] = "built+verified+plan_emitted"
    _record_ledger(run_dir, record)
    print("\nSALES/CHECKOUT BUILD: PLAN EMITTED (awaiting delegated agent-browser push)")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Offline deterministic self-test (no network, no kie.ai spend, no GHL call)
# ---------------------------------------------------------------------------
def _selftest() -> int:
    fails: List[str] = []

    # 1) THE GATE — every branch, matching upsell-questions.json's waiver semantics.
    def _gate(pre: dict) -> dict:
        return resolve_sales_checkout_gate({"pre_presentation_capture": pre})

    g = _gate({})
    if g["decision"] != "defer":
        fails.append(f"gate(absent) expected defer, got {g['decision']}")
    g = _gate({"WANT_SALES_CHECKOUT": ""})
    if g["decision"] != "defer":
        fails.append(f"gate(blank) expected defer, got {g['decision']}")
    g = _gate({"WANT_SALES_CHECKOUT": "yes"})
    if g["decision"] != "build":
        fails.append(f"gate(yes) expected build, got {g['decision']}")
    g = _gate({"WANT_SALES_CHECKOUT": "YES"})
    if g["decision"] != "build":
        fails.append(f"gate(YES, case-insensitive) expected build, got {g['decision']}")
    g = _gate({"WANT_SALES_CHECKOUT": "no"})
    if g["decision"] != "fail_closed" or AF_WAIVER_MISSING not in g["detail"]:
        fails.append(f"gate(no, no reason) expected fail_closed/{AF_WAIVER_MISSING}, got {g}")
    g = _gate({"WANT_SALES_CHECKOUT": "no", "SALES_CHECKOUT_DECLINED_REASON": "  "})
    if g["decision"] != "fail_closed":
        fails.append(f"gate(no, blank reason) expected fail_closed, got {g['decision']}")
    g = _gate({"WANT_SALES_CHECKOUT": "no", "SALES_CHECKOUT_DECLINED_REASON": "ok"})
    if g["decision"] != "fail_closed":
        fails.append(f"gate(no, 2-char reason) expected fail_closed (< {MIN_WAIVER_QUOTE_CHARS} chars), got {g['decision']}")
    g = _gate({"WANT_SALES_CHECKOUT": "no",
              "SALES_CHECKOUT_DECLINED_REASON": "We already have a checkout page we like."})
    if g["decision"] != "waived" or g.get("quote") != "We already have a checkout page we like.":
        fails.append(f"gate(no, real reason) expected waived with quote preserved, got {g}")
    g = _gate({"WANT_SALES_CHECKOUT": "maybe"})
    if g["decision"] != "fail_closed" or AF_VALUE_UNRECOGNIZED not in g["detail"]:
        fails.append(f"gate(maybe) expected fail_closed/{AF_VALUE_UNRECOGNIZED}, got {g}")

    # 2) COPY — deterministic, content present.
    brief = {
        "OFFER_NAME": "The Momentum Method",
        "TRANSFORMATION_PROMISE": "Go from stuck to shipped in 30 days.",
        "AUDIENCE": "overwhelmed solo founders",
        "CTA_ACTION": "Join The Momentum Method",
        "FINAL_PRICE": "$997",
        "PRICE_MODE": "one-time",
        "PRIMARY_OBJECTION": "I don't have time for another program.",
        "PROOF_ASSETS": "312 founders shipped their first launch.",
        "HOOK_SEED": "You don't need more time. You need momentum.",
        "BRAND_PRIMARY": "#1a2b6d",
    }
    sales_md = build_sales_copy(brief, "Test Client")
    checkout_md = build_checkout_copy(brief, "Test Client")
    if brief["HOOK_SEED"] not in sales_md or brief["OFFER_NAME"] not in sales_md:
        fails.append("sales copy missing baked content strings")
    if brief["OFFER_NAME"] not in checkout_md:
        fails.append("checkout copy missing offer name")

    # 3) DESIGN PROMPT — band + content-gate pass, adversarial fails.
    brand = resolve_brand(Path("/nonexistent"), {"deck_brief": brief})
    sales_fields = _content_fields_for_page("sales", brief, "Test Client")
    checkout_fields = _content_fields_for_page("checkout", brief, "Test Client")
    sales_prompt = build_design_prompt(page_role="sales", brand=brand, client_name="Test Client",
                                       fields=sales_fields, page_index=1, page_count_total=2)
    checkout_prompt = build_design_prompt(page_role="checkout", brand=brand, client_name="Test Client",
                                          fields=checkout_fields, page_index=2, page_count_total=2)
    for pid, prompt, fields in (("sales-hero", sales_prompt, sales_fields),
                                ("checkout-hero", checkout_prompt, checkout_fields)):
        n = len(prompt.strip())
        if not (PROMPT_FLOOR <= n <= PROMPT_CEILING):
            fails.append(f"{pid}: prompt {n} chars outside {PROMPT_FLOOR}-{PROMPT_CEILING} band")
        try:
            assert_content_in_prompt(pid, fields, prompt)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"{pid}: content gate REJECTED a content-bearing prompt: {exc}")
        try:
            _assert_prompt_band(prompt, pid)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"{pid}: band assertion failed on a valid prompt: {exc}")

    # 3b) adversarial: zero-content page MUST be refused.
    try:
        assert_content_in_prompt("adv-empty", {}, "DESIGN A LANDING PAGE BACKGROUND...")
        fails.append("content gate ACCEPTED a page with ZERO content strings")
    except RuntimeError as exc:
        if AF_PROMPT_NO_CONTENT not in str(exc):
            fails.append(f"zero-content rejection did not name the AF code: {exc}")
    # 3c) adversarial: wireframe directive present, even WITH content, MUST be refused.
    try:
        assert_content_in_prompt("adv-wire", sales_fields,
                                 "This is the BACKGROUND ONLY for a landing page. NO text.")
        fails.append("content gate ACCEPTED a prompt carrying the BACKGROUND ONLY wireframe directive")
    except RuntimeError as exc:
        if AF_PROMPT_NO_CONTENT not in str(exc):
            fails.append(f"wireframe rejection did not name the AF code: {exc}")

    # 4) HTML — content strings present, ghl_rest_canvas.html_fragment compatible,
    #    images-as-media-links gate rejects an external src and accepts a GHL one.
    marker = "ZHC-SC-selftest"
    sales_html = build_page_html(page_role="sales", brand=brand, client_name="Test Client",
                                 fields=dict(sales_fields, proof=brief["PROOF_ASSETS"]),
                                 hero_image_src=None, marker=marker)
    missing = _html_content_strings_present(sales_html, sales_fields)
    if missing:
        fails.append(f"sales HTML missing content strings: {missing}")

    try:
        rc = _import_ghl_rest_canvas()
    except Exception as exc:  # noqa: BLE001
        fails.append(f"could not import ghl_rest_canvas.py: {exc}")
        rc = None

    if rc is not None:
        # bare fragment passthrough (no full-document wrapper) must be a no-op.
        try:
            frag = rc.html_fragment(sales_html)
            if frag.strip() != sales_html.strip():
                fails.append("html_fragment() mutated a bare body-level fragment (should be a no-op)")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"html_fragment() raised on a valid bare fragment: {exc}")

        # images-as-media-links gate: an external hot-link MUST be rejected.
        bad_html = sales_html.replace(
            "<div class=\"zhc-sales-page\">",
            "<div class=\"zhc-sales-page\"><img src=\"https://evil.example.com/hero.png\">",
        )
        try:
            rc.html_fragment(bad_html, require_ghl_media=True)
            fails.append("html_fragment(require_ghl_media=True) ACCEPTED a non-GHL external <img> src")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            fails.append(f"unexpected exception rejecting external <img>: {exc}")

        # a genuine GHL-media-storage src MUST be accepted.
        good_html = sales_html.replace(
            "<div class=\"zhc-sales-page\">",
            "<div class=\"zhc-sales-page\"><img src=\"https://storage.googleapis.com/msgsndr/loc123/hero.png\">",
        )
        try:
            rc.html_fragment(good_html, require_ghl_media=True)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"html_fragment(require_ghl_media=True) REJECTED a genuine GHL media src: {exc}")

        # new_page_blob() — pure, offline, must succeed for a valid fragment and
        # internally pass assert_renderable_shape (raises AssertionError otherwise).
        try:
            blob = rc.new_page_blob(sales_html, surface="funnel",
                                    primary_color=brand["primary"], secondary_color=brand["secondary"])
            if not isinstance(blob, dict) or not blob.get("sections"):
                fails.append("new_page_blob() returned an unexpected shape")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"new_page_blob() raised on a valid fragment: {exc}")

        # funnel_create/step_create/page_autosave WITHOUT session -- pure/local,
        # no browser_manager import, no network call of any kind.
        try:
            fc = rc.funnel_create("loc123", "Test Client — Sales/Checkout", funnel_type="funnel")
            if fc.get("method") != "POST" or "argv" in fc:
                fails.append(f"funnel_create() without session produced an unexpected step: {fc.keys()}")
            sc = rc.step_create("FUNNEL_ID", "Sales", "test-client-sales")
            if sc.get("method") != "POST" or "argv" in sc:
                fails.append(f"step_create() without session produced an unexpected step: {sc.keys()}")
            pa = rc.page_autosave("SALES_PAGE_ID", blob, funnel_id="FUNNEL_ID", page_version=1)
            if pa.get("method") != "POST" or "argv" in pa or pa["body"]["pageVersion"] != 2:
                fails.append(f"page_autosave() without session produced an unexpected step: {pa}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"offline ghl_rest_canvas step construction raised: {exc}")

        # the full plan builder end to end (pure, offline).
        try:
            checkout_html = build_page_html(
                page_role="checkout", brand=brand, client_name="Test Client",
                fields=dict(checkout_fields, order_line="The Momentum Method — $997",
                           reassurance="Secure checkout."),
                hero_image_src=None, marker=marker,
            )
            plan = build_ghl_push_plan(
                location_id="loc123", funnel_name="Test Client — Sales/Checkout",
                deck_slug="test-client", sales_html=sales_html, checkout_html=checkout_html, brand=brand,
            )
            if len(plan.get("sequence", [])) != 5:
                fails.append(f"build_ghl_push_plan(): expected a 5-step sequence, got {len(plan.get('sequence', []))}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"build_ghl_push_plan() raised on valid input: {exc}")

    # 5) receipt verification — absent / placeholder / real.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        status, detail, _ = verify_push_receipt(rd)
        if status is not None:
            fails.append(f"verify_push_receipt(absent) expected None (not-yet-executed), got {status}")

        sc_dir = rd / "working" / "sales-checkout"
        sc_dir.mkdir(parents=True)
        (sc_dir / "build_receipt.json").write_text(json.dumps({
            "preview_urls": ["https://example.com/preview/abc"],
            "funnel_id": "f1",
        }))
        status, detail, _ = verify_push_receipt(rd)
        if status is not False:
            fails.append(f"verify_push_receipt(placeholder host) expected False, got {status}")

        (sc_dir / "build_receipt.json").write_text(json.dumps({
            "preview_urls": ["https://app.convertandflow.com/preview/abc123"],
            "funnel_id": "z20T0real",
        }))
        status, detail, _ = verify_push_receipt(rd)
        if status is not True:
            fails.append(f"verify_push_receipt(real) expected True, got {status} ({detail})")

        # 6) ledger round-trip.
        _record_ledger(rd, {"status": "built+verified+pushed", "a": 1})
        _record_ledger(rd, {"b": 2})
        ledger = json.loads((rd / "working" / "checkpoints" / "sales_checkout.json").read_text())
        if ledger.get("a") != 1 or ledger.get("b") != 2:
            fails.append(f"ledger round-trip lost a field: {ledger}")

    if fails:
        print("sales_checkout_builder selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("sales_checkout_builder selftest -> PASS "
          "(gate: defer/build/waived/fail_closed x2 + case-insensitive; copy content; "
          "prompt band + content-gate pass/zero-content-refuse/wireframe-refuse; HTML "
          "content + ghl_rest_canvas.html_fragment/images-as-media-links/new_page_blob/"
          "funnel_create/step_create/page_autosave (all offline, no session); receipt "
          "absent/placeholder/real; ledger round-trip)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
