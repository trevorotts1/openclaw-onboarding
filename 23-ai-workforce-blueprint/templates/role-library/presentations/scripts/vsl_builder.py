#!/usr/bin/env python3
"""
vsl_builder.py — the VSL (video sales letter) page executor (Wave C, C3).

TEMPLATES the Loop 2C flow (proven by hand 2026-08-07, render-verified):
    kie.ai design  ->  agent copy  ->  HTML+gate  ->  GHL funnel push (Skill 6, REST)
See GAUNTLET-LOOP-WORK/LOOP2C-VSL-SALES-CHECKOUT-WEBSITE.md and this department's own
sops/VSL-BUILDER-SOP.md (written concurrently by C5 — read in full before this module
was written; every section reference below is to that SOP). This module templates the
FLOW ONLY — it carries no client name, no client copy, no funnel id, no branding. Every
client-specific value is resolved at runtime from the run's own intake.json, exactly
like sales_checkout_builder.py (C2, the closest sibling — this module deliberately
mirrors its architecture line for line wherever the two executors overlap, per
VSL-BUILDER-SOP.md §3 step 4: "Unit C3 must resolve [the GHL push] caveat the same way
C2 does — ideally the SAME resolution, since both executors call the same push
mechanism").

THE GATE — WANT_VSL_PAGE (upsell-questions.json v1.0.0, U026 waiver mechanic)
-------------------------------------------------------------------------------------
Read from working/copy/intake.json's `pre_presentation_capture.WANT_VSL_PAGE`
(intake_writer.py's ID_TO_FIELD/PRE_CAPTURE_FIELDS mapping — the SAME field the app
writes). Per upsell-questions.json's `waiver_field_mapping.vsl_page` (toggle=
want_vsl_page, reason=vsl_page_declined_reason): unlike WANT_SALES_CHECKOUT (default
YES), **this question defaults to NO** — "Default 'no' (video must exist for a VSL
page)." A "no" is still a CLIENT WAIVER and REQUIRES the client's own verbatim
declined-reason — "it is never inferred from silence and never written by the
assistant." Four outcomes, never conflated (identical shape to
sales_checkout_builder.resolve_sales_checkout_gate — the SAME waiver discipline, an
inverted default):
    ABSENT / BLANK           -> DEFER   (never treated as a decline; the question was
                                          never asked/answered in this run)
    "yes"                    -> BUILD (subject to the hard video dependency below)
    "no" + real quote        -> WAIVED  (legitimately gated OUT; not a failure — the
                                          SAME externally observable behaviour as DEFER:
                                          exit 0, nothing built)
    "no" + missing/blank quote,
    or any unrecognized value -> FAIL CLOSED (a self-authored "no" is refused, mirrors
                                          presentation_job/waivers.py's own
                                          client_request_quote >= 3-char floor)

THE HARD VIDEO DEPENDENCY — MUST run after P9.6-WEBINAR-VIDEO (VSL-BUILDER-SOP.md §2)
-------------------------------------------------------------------------------------
The VSL page embeds/links the produced webinar video. `P9.6-WEBINAR-VIDEO`
(build_webinar_video.py, order 8.92) is what produces the artifact and uploads it to
GHL. This module NEVER guesses the artifact's filename or location: it imports
build_webinar_video.py's own `WEBINAR_FILENAME_TEMPLATE` + `resolve_deck_slug` (the
canonical symbols) rather than re-deriving them, so the two executors can never drift.
The dependency check runs BEFORE any copy/design/HTML/push work:
    1. resolve <run_dir>/working/delivery/{deck_slug}-WEBINAR.mp4 via the imported
       template (never a literal string in this file).
    2. the file must EXIST (AF-VSL-NO-VIDEO if not).
    3. the file must pass ghl_media.verify_video() — the department's own canonical,
       already-proven local probe (exists, non-empty, <=500MB v3 ceiling, real MP4
       `ftyp` box) — reused here verbatim, never reimplemented (AF-VSL-NO-VIDEO if it
       fails the probe).
A "yes" that fails this dependency FAILS LOUD (exit 5) — it never silently builds a
page with a missing/broken video embed and never falls back to a placeholder video
(VSL-BUILDER-SOP.md §2, §5).

THE GHL PUSH — WHY THIS IS A DELEGATED RECEIPT, NOT A LIVE DRIVE
-------------------------------------------------------------------------------------
Identical seam to sales_checkout_builder.py (read there for the full citation chain):
06-ghl-install-pages/tools/ghl_rest_canvas.py is "THE GLUE, NOT THE CLICKER" — every
/funnels/* route is Cloudflare-WAF-gated and MUST run inside a live agent-browser eval
context; funnel_create()/step_create()/page_autosave() build the exact REST step but
never make a network call themselves when called WITHOUT a `session` kwarg (as this
offline builder does — 100% pure/local, no browser_manager import attempted). This
module builds the funnel/step/page-autosave REST steps with ghl_rest_canvas's real
functions (never reimplementing GHL REST), writes them as an ordered execution plan
(`working/vsl/ghl_push_plan.json`) for an agent holding a live agent-browser session to
execute, then verifies the resulting `working/vsl/build_receipt.json` before calling
the phase pushed. Absence of a receipt is NOT a failure — "plan emitted, awaiting
delegated execution" (exit 0); a PRESENT but placeholder/fabricated receipt IS a
failure (exit 4). ADDITIONALLY (VSL-specific, not in the sales/checkout sibling):
Loop 2C's real, proven build put sales+checkout+VSL as THREE PAGES inside ONE funnel
(GAUNTLET-LOOP-WORK/LOOP2C…md §CURRENT STATE — funnel z20T0cPnEoh2kCep5u6I hosted all
three). When this run's sales_checkout_builder.py ledger already recorded a verified
push, this module reuses that SAME funnel_id (skips its own funnel_create) instead of
creating a second funnel for one client — the closer-to-Loop-2C resolution, and it
degrades safely to "create my own funnel" when no such record exists.

THE VIEWER GATE (VSL-BUILDER-SOP.md §4)
-------------------------------------------------------------------------------------
Loop 2C's proven design: a gate at roughly 3-8 minutes into the video ("after the
first big revelation") that pauses playback and blocks further seeking until the
viewer submits first name / email / cell. The SOP requires the timestamp be DERIVED
from the run's own `working/checkpoints/webinar_timing.json` track, never hardcoded —
`resolve_gate_timestamp()` below picks the real slide-boundary inside the [180s, 480s]
window closest to its midpoint, falling back to a clamped/derived value when the
track is thin or absent. LEAD-CAPTURE MECHANISM DECISION (the SOP asks C3 to record
this explicitly, §4): this module ships a lightweight NATIVE HTML form embedded in the
gate overlay (not the heavier universal-sops/form-craft/ engine) — the gate is a
client-side JS mechanic (pause + seek-block + reveal-on-submit) that a governed agent
wires to the client's real GHL contact/workflow endpoint at deployment time; a fleet
template cannot carry a client's live endpoint (documented TODO left in the emitted
HTML, never fabricated as if wired).

NO CLIENT NAMES OR CLIENT-SPECIFIC CONTENT — this is a fleet-wide template. Loop 2C's
real pages were built for one client and deliberately kept out of this repo.

USAGE
    python3 scripts/vsl_builder.py --run-dir <run_dir> [--skip-design] [--no-push]
    python3 scripts/vsl_builder.py --selftest

    --run-dir     The governed pipeline run dir (reads working/copy/intake.json +
                  working/delivery/{deck_slug}-WEBINAR.mp4 + working/checkpoints/
                  webinar_timing.json + working/checkpoints/media_library.json).
    --skip-design Reuse an already-downloaded hero render (working/vsl/renders/)
                  without a fresh kie.ai run. Copy + HTML + plan + receipt-check only.
    --no-push     Skip the front-door-nonce requirement and the GHL push plan/receipt
                  steps entirely (offline smoke build: copy + design + HTML only, no
                  client GHL write, no push-plan artifact). The video dependency check
                  still runs — a video-less page is never built, pushed or not.
    --selftest    Deterministic offline self-test (no network, no kie.ai spend, no GHL
                  call of any kind, no real video/audio — every ghl_rest_canvas call
                  below is made WITHOUT a session, which is pure/local by
                  construction).

FRONT-DOOR NONCE (mirrors build_deck.py / workbook_builder.py / build_webinar_video.py
/ sales_checkout_builder.py)
    presentation-canonical-entry.sh mints OC_DECK_ENTRY_NONCE + the run-scoped 0600
    file <run-dir>/working/checkpoints/.canonical-entry-nonce. A hand-rolled invocation
    that would spend kie.ai money or touch a client's GHL funnel is refused (exit 2,
    AF-CANONICAL-RENDER-BYPASS) unless --no-push. --no-push offline smoke builds are
    exempt (no client GHL write is possible on that path).

RUN-DIR / ARTIFACT / STATE CONVENTIONS
    This executor deliberately does NOT touch presentation_job's engine-internal
    StateStore/RunLock (presentation_job/state.py) — mirroring build_webinar_video.py,
    workbook_builder.py and sales_checkout_builder.py, none of which do either; all
    four are standalone phase executors dispatched BY the engine, not engine-state
    manipulators. Its own artifact-validity discipline (existence -> non-empty ->
    shape/magic check, fail with a named reason) mirrors presentation_job/artifacts.py's
    validate_* predicate ORDER exactly (see verify_video_dependency below), and its
    working set is intentionally phase-scoped under working/vsl/ + a single
    working/checkpoints/vsl.json ledger (FIX-20 discipline, presentation_job/
    workingset.py), so a compaction mid-build never loses more than one phase's state.

EXIT CODES
    0  — DEFERRED (flag absent -- nothing to do this run), or WAIVED (client declined
         with a recorded reason -- correctly gated out), or BUILT (copy+design+
         HTML+plan emitted, receipt not yet present -- awaiting delegated
         agent-browser execution), or PUSHED (a valid delegated receipt was found and
         verified)
    1  — kie.ai design/render failure
    2  — fatal configuration error (no API key, missing run-dir, refused nonce)
    3  — GATE BLOCKED: a bare "no" with no verbatim client reason, or an unrecognized
         WANT_VSL_PAGE value (AF-VSL-WAIVER-MISSING / AF-VSL-VALUE-UNRECOGNIZED)
    4  — VERIFY FAILED: a present build_receipt.json is placeholder/fabricated (no real
         preview_urls, or no funnel_id), or an assembled artifact failed its content
         gate
    5  — AF-VSL-NO-VIDEO: elected ("yes") but the P9.6 webinar video artifact is
         missing or fails ghl_media.verify_video()'s local probe -- fail-closed, never
         a placeholder video
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
EXIT_VIDEO_MISSING = 5

# ---------------------------------------------------------------------------
# Waiver mechanic constants (mirrors sales_checkout_builder.py's own floor, which
# mirrors presentation_job/waivers.py's: `if len(quote) < 3: raise WaiverError(...
# "a waiver the agent wrote for itself is not a waiver")`) and upsell-questions.json's
# storeTarget field names for THIS question (want_vsl_page, not want_sales_checkout).
# ---------------------------------------------------------------------------
MIN_WAIVER_QUOTE_CHARS = 3
WANT_FIELD = "WANT_VSL_PAGE"
REASON_FIELD = "VSL_PAGE_DECLINED_REASON"
AF_WAIVER_MISSING = "AF-VSL-WAIVER-MISSING"
AF_VALUE_UNRECOGNIZED = "AF-VSL-VALUE-UNRECOGNIZED"
AF_PROMPT_NO_CONTENT = "AF-VSL-PROMPT-NO-CONTENT"
AF_NO_VIDEO = "AF-VSL-NO-VIDEO"

# ---------------------------------------------------------------------------
# Design-prompt band (mirrors workbook_builder.py / sales_checkout_builder.py's
# Presentations rich-prompt gate: 9,000-18,000 stripped chars — VSL-BUILDER-SOP.md
# §3 step 2, explicitly NOT Loop 2C's looser 5,000-19,000 research band).
# ---------------------------------------------------------------------------
PROMPT_FLOOR = 9000
PROMPT_CEILING = 18000

ASPECT_RATIO = "16:9"
RESOLUTION = "2K"

# The viewer-gate window (VSL-BUILDER-SOP.md §4: "roughly 3-8 minutes ... after the
# first big revelation"). resolve_gate_timestamp() derives the REAL timestamp inside
# this window from webinar_timing.json; these are the window bounds, never the
# timestamp itself.
VSL_GATE_MIN_SEC = 180.0
VSL_GATE_MAX_SEC = 480.0

# Front-door nonce (identical contract to workbook_builder.py / build_deck.py /
# build_webinar_video.py / sales_checkout_builder.py).
ENTRY_NONCE_REL = Path("working") / "checkpoints" / ".canonical-entry-nonce"

# Brand defaults when intake carries no palette (mirrors workbook_builder.py's /
# sales_checkout_builder.py's fallback).
DEFAULT_PRIMARY = "#212748"
DEFAULT_SECONDARY = "#B38456"
DEFAULT_ACCENT = "#C49A70"
DEFAULT_BASE = "#F2E6D7"
DEFAULT_INK = "#1A1A1A"

# Placeholder hosts a delegated receipt's preview_urls must never resolve to (mirrors
# sales_checkout_builder.py's PLACEHOLDER_HOSTS, itself mirroring
# 56-sales-page-assets/run_sales_page_assets.py's PLACEHOLDER_HOSTS).
PLACEHOLDER_HOSTS = (
    "example.com", "example.org", "example.net", "example.edu", "invalid",
    "localhost", "127.0.0.1", "0.0.0.0", "test.com", "changeme.com", "todo.com",
)

WIREFRAME_BAN_PHRASES = (
    "background only", "background-only", "no text", "wireframe", "blank template",
    "blank page background",
)


class VslBuildError(RuntimeError):
    """Raised on a hard, fail-closed build failure (message names the failing gate)."""


# ---------------------------------------------------------------------------
# Optional shared prompt-gate (degrade gracefully -- mirrors workbook_builder.py /
# sales_checkout_builder.py).
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
# same discipline kie_generate.py's HIGH-3 fix, sales_checkout_builder.py's
# _find_ghl_rest_canvas_dir, and _import_prompt_gate all use).
# ---------------------------------------------------------------------------
def _here() -> Path:
    return Path(__file__).resolve().parent


def _find_ghl_rest_canvas_dir() -> Optional[Path]:
    """Walk every ancestor of this file looking for the sibling Skill-6 tools dir
    that ships ghl_rest_canvas.py. Identical to sales_checkout_builder.py's own
    resolver — no absolute path is ever assumed."""
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
    """The sibling department module (co-located with this script). Used to (a) host
    the kie-rendered hero PNG in the GHL media library before it can be referenced by
    a GHL-media-storage <img src>, and (b) reuse its canonical verify_video() local
    probe for the hard video dependency -- never reimplemented here."""
    here = _here()
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import ghl_media  # noqa: E402
    return ghl_media


def _import_build_webinar_video():
    """The sibling P9.6 executor -- imported ONLY to reuse its real, canonical
    WEBINAR_FILENAME_TEMPLATE + resolve_deck_slug. This module never re-derives the
    webinar filename convention (the task rule: 'do not guess the filename')."""
    here = _here()
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import build_webinar_video  # noqa: E402
    return build_webinar_video


# ---------------------------------------------------------------------------
# intake.json helpers (mirror sales_checkout_builder.py)
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


def resolve_brand(run_dir: Path, intake: dict) -> Dict[str, str]:
    brief = resolve_brief(intake)
    primary = _hex_color(brief.get("BRAND_PRIMARY"), DEFAULT_PRIMARY)
    return {
        "primary": primary,
        "secondary": DEFAULT_SECONDARY,
        "accent": DEFAULT_ACCENT,
        "base": DEFAULT_BASE,
        "ink": DEFAULT_INK,
    }


def resolve_deck_slug(run_dir: Path) -> str:
    """THE canonical deck_slug for this entire module -- delegates to
    build_webinar_video.resolve_deck_slug() (single source of truth, so the video
    filename this module checks and the slug it uses to name its own artifacts can
    never disagree)."""
    bwv = _import_build_webinar_video()
    return bwv.resolve_deck_slug(run_dir)


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
    return resolve_deck_slug(run_dir).replace("-", " ").title()


# ---------------------------------------------------------------------------
# THE GATE — resolve_vsl_gate()
# ---------------------------------------------------------------------------
def resolve_vsl_gate(intake: dict) -> Dict[str, Any]:
    """Resolve WANT_VSL_PAGE against upsell-questions.json's waiver_field_mapping
    (U026), inverted-default variant. Returns
    {"decision": "defer"|"build"|"waived"|"fail_closed", "detail": str, ...}.

    Never conflates "absent" with "declined" -- silence is NOT consent (upsell-
    questions.json's own words, verbatim, for BOTH upsell questions -- only the
    DEFAULT differs). A "no" ALWAYS requires a real, non-empty verbatim client reason
    at VSL_PAGE_DECLINED_REASON or the gate fails closed."""
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
                "intake never asked/answered the upsell question (this question's own "
                "default is 'no' unless the client explicitly opts in). DEFERRING: an "
                "absent answer is NEVER treated as a decline (silence is not consent)."
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
                "(upsell-questions.json waiver_field_mapping.vsl_page; "
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
# THE HARD VIDEO DEPENDENCY — verify_video_dependency() (AF-VSL-NO-VIDEO)
# ---------------------------------------------------------------------------
def resolve_video_artifact(run_dir: Path, deck_slug: str) -> Path:
    """The REAL P9.6 webinar video path -- resolved via build_webinar_video.py's own
    WEBINAR_FILENAME_TEMPLATE, never a literal string in this file."""
    bwv = _import_build_webinar_video()
    name = bwv.WEBINAR_FILENAME_TEMPLATE.format(deck_slug=deck_slug)
    return run_dir / "working" / "delivery" / name


def verify_video_dependency(run_dir: Path, deck_slug: str) -> Path:
    """AF-VSL-NO-VIDEO: verify the P9.6 webinar video artifact exists AND is non-empty
    (and passes ghl_media's own canonical local MP4 probe) BEFORE any VSL work starts.
    Fails closed (VslBuildError) with the exact path checked -- never a placeholder
    video, never a silent degrade (VSL-BUILDER-SOP.md §2, §5)."""
    video_path = resolve_video_artifact(run_dir, deck_slug)
    if not video_path.is_file():
        raise VslBuildError(
            f"{AF_NO_VIDEO}: webinar video artifact not found at {video_path!r}. "
            "The VSL page embeds/links the P9.6 webinar video -- P-U-VSL-PAGE MUST run "
            "AFTER P9.6-WEBINAR-VIDEO (build_webinar_video.py), never before. Run the "
            "webinar phase first, then re-run this builder."
        )
    ghl_media = _import_ghl_media()
    if not ghl_media.verify_video(video_path):
        size = video_path.stat().st_size if video_path.exists() else 0
        raise VslBuildError(
            f"{AF_NO_VIDEO}: webinar video artifact {video_path!r} exists ({size} bytes) "
            "but failed ghl_media.verify_video()'s local probe (empty / over the 500MB "
            "v3 ceiling / missing the MP4 'ftyp' box) -- refusing to build a VSL page "
            "around a broken video artifact (fail-closed)."
        )
    return video_path


def resolve_video_ghl_url(run_dir: Path, deck_slug: str) -> Tuple[Optional[str], Optional[str]]:
    """Read the P9.6 webinar's hosted GHL url from working/checkpoints/media_library.json
    (build_webinar_video._record_webinar_in_ledger's own `webinar_mp4.ghl_url`). Returns
    (url_or_None, cross_check_warning_or_None) -- the warning fires when the ledger's
    own recorded deck_slug does not match THIS run's deck_slug (VSL-BUILDER-SOP.md §8:
    "cross-referenced ... so a QC pass can confirm the VSL page embeds THIS run's
    video, not a stale one")."""
    ledger = _read_json(run_dir / "working" / "checkpoints" / "media_library.json")
    rec = ledger.get("webinar_mp4") if isinstance(ledger.get("webinar_mp4"), dict) else {}
    url = rec.get("ghl_url")
    url = url.strip() if isinstance(url, str) and url.strip() else None
    warning = None
    rec_slug = rec.get("deck_slug")
    if rec_slug and str(rec_slug) != deck_slug:
        warning = (
            f"media_library.json webinar_mp4.deck_slug={rec_slug!r} != this run's "
            f"deck_slug={deck_slug!r} -- verify this is THIS run's video, not a stale one."
        )
    return url, warning


# ---------------------------------------------------------------------------
# THE VIEWER GATE TIMESTAMP — resolve_gate_timestamp() (VSL-BUILDER-SOP.md §4)
# ---------------------------------------------------------------------------
def resolve_gate_timestamp(run_dir: Path, *, min_sec: float = VSL_GATE_MIN_SEC,
                           max_sec: float = VSL_GATE_MAX_SEC) -> Dict[str, Any]:
    """Derive the VSL viewer-gate timestamp from the run's OWN webinar_timing.json
    track (P9.6's step 1 output) -- never a fixed hardcoded second count. Picks the
    slide-boundary (`audio_start`) closest to the window midpoint that falls inside
    [min_sec, max_sec] ("after the first big revelation", Loop 2C's own spec). Falls
    back to a clamped/derived value when the track is absent or the talk is shorter
    than the window, and to the window midpoint when nothing at all is known."""
    timing = _read_json(run_dir / "working" / "checkpoints" / "webinar_timing.json")
    entries = timing.get("timing") if isinstance(timing.get("timing"), list) else []
    midpoint = (min_sec + max_sec) / 2.0
    candidates = [
        e for e in entries
        if isinstance(e, dict) and isinstance(e.get("audio_start"), (int, float))
        and min_sec <= float(e["audio_start"]) <= max_sec
    ]
    if candidates:
        best = min(candidates, key=lambda e: abs(float(e["audio_start"]) - midpoint))
        return {
            "seconds": round(float(best["audio_start"]), 3),
            "source": f"webinar_timing.json slide {best.get('slide')} audio_start",
            "window": [min_sec, max_sec],
        }
    total = timing.get("total_audio_sec")
    if isinstance(total, (int, float)) and total > 0:
        lo = min_sec
        hi = max(min_sec, min(max_sec, float(total) - 1.0))
        clamped = min(max(lo, float(total) * 0.5), hi) if hi >= lo else lo
        return {
            "seconds": round(clamped, 3),
            "source": (
                "webinar_timing.json present but no slide boundary fell inside the "
                f"{min_sec:.0f}-{max_sec:.0f}s window (total_audio_sec={total}) -- clamped"
            ),
            "window": [min_sec, max_sec],
        }
    return {
        "seconds": midpoint,
        "source": "no webinar_timing.json track found -- window midpoint default",
        "window": [min_sec, max_sec],
    }


# ---------------------------------------------------------------------------
# COPY — deterministic, offline, template-driven from the run's own intake brief.
# No fabricated specifics: every field falls back to a generic, honest placeholder
# phrase (mirrors sales_checkout_builder.py's own build_sales_copy idiom) rather than
# inventing a client claim.
# ---------------------------------------------------------------------------
def build_vsl_copy(brief: Dict[str, Any], client_name: str) -> str:
    offer = brief.get("OFFER_NAME") or "this offer"
    promise = brief.get("TRANSFORMATION_PROMISE") or "a clear, stated transformation"
    audience = brief.get("AUDIENCE") or "the stated audience"
    cta = brief.get("CTA_ACTION") or "Watch The Full Training"
    hook = brief.get("HOOK_SEED") or promise
    objection = brief.get("PRIMARY_OBJECTION") or "the audience's most common hesitation"
    proof = brief.get("PROOF_ASSETS") or "the client's real results and proof assets"
    return "\n".join([
        f"# {client_name} — VSL (Video Sales Letter) Page Copy",
        "",
        "## Hero Headline",
        str(hook),
        "",
        "## Subheadline",
        f"{offer} for {audience}.",
        "",
        "## The Video",
        f"This page presents the department's own webinar video ({offer}) as the "
        "centerpiece; the copy below frames it, it does not replace it.",
        "",
        "## Why Keep Watching (pre-gate teaser)",
        str(promise),
        "",
        "## The Viewer Gate",
        "A lead-capture gate appears partway through the video, after the first big "
        "revelation, requesting first name / email / cell before playback continues.",
        "",
        "## Objection Handled",
        str(objection),
        "",
        "## Proof",
        str(proof),
        "",
        "## Call To Action",
        str(cta),
    ]) + "\n"


def _vsl_content_fields(brief: Dict[str, Any], client_name: str) -> Dict[str, str]:
    """The verbatim content strings the design prompt must bake into the image --
    mirrors sales_checkout_builder.py's _content_fields_for_page content-in-image
    discipline."""
    return {
        "headline": str(brief.get("HOOK_SEED") or brief.get("TRANSFORMATION_PROMISE") or client_name),
        "subhead": f"{brief.get('OFFER_NAME') or 'This training'} for {brief.get('AUDIENCE') or 'you'}.",
        "cta": str(brief.get("CTA_ACTION") or "Watch The Full Training"),
    }


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _page_content_strings(fields: Dict[str, str]) -> List[str]:
    return [v.strip() for v in fields.values() if isinstance(v, str) and len(v.strip()) >= 3]


def assert_content_in_prompt(page_id: str, fields: Dict[str, str], prompt: str) -> None:
    """AF-VSL-PROMPT-NO-CONTENT -- fail-closed PRE-SUBMIT content gate. Mirrors
    sales_checkout_builder.py's assert_content_in_prompt exactly: a wireframe/
    background-only directive, or a page carrying zero content strings, or content not
    baked verbatim, is refused before any paid kie.ai render."""
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


def build_design_prompt(*, brand: Dict[str, str], client_name: str,
                        fields: Dict[str, str]) -> str:
    """Compose a content-in-image VSL hero design prompt (9,000-18,000 stripped
    chars), templating workbook_builder.py's / sales_checkout_builder.py's proven
    content-in-image technique for a video-player-centric marketing hero."""
    prim, sec, acc = brand["primary"], brand["secondary"], brand["accent"]
    base, ink = brand["base"], brand["ink"]
    headline = fields.get("headline", "")
    subhead = fields.get("subhead", "")
    cta = fields.get("cta", "")
    prompt = f"""[ARCHETYPE ZHC-VSL-PAGE-HERO]
DESIGN A SINGLE FULL-BLEED WEB PAGE HERO DESIGN, LANDSCAPE, {ASPECT_RATIO} ASPECT, {RESOLUTION}.
This is a DESIGNED, CONTENT-RICH video-sales-letter (VSL) page hero for {client_name}.
Render the page's REAL content (headline, subheadline, call-to-action label) baked into
the image by the text-to-image engine, in the brand system below. Every quoted string
must be rendered VERBATIM, letter-for-letter.

=== PAGE ROLE & WHAT THIS PAGE IS FOR ===
This page is: VSL PAGE HERO. Its job is to frame the department's own webinar video as
the centerpiece of a long-form video sales letter, earning the click to press play and
setting up the promise the video itself delivers on. The visitor reads top-to-bottom:
headline, subheadline, a large centered video-player mockup, then the call-to-action.
The page must stand alone as a finished, premium marketing surface, not a placeholder
shell, and must read clearly at a glance on both desktop and mobile crops.

=== BRAND LOCKUP ===
Client: {client_name}. Grade: premium, confident, story-driven, editorial.
Brand palette (use these EXACT hex values, no substitutions):
  Primary {prim} — header band, CTA button fill, play-button ring.
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
centered beneath the video-player mockup):
  {cta!r}

=== VERBATIM + SPELLING-LOCK ===
Render EVERY quoted string above letter-for-letter, exactly as written, spelled exactly,
no paraphrasing, no substitution, no reordering, no typo, no garble, no truncation, no
ellipsis unless it is in the source string. The quoted strings above are the ONLY text on
this page beyond the {client_name} wordmark and a single centered PLAY glyph inside the
video-player mockup. Text must read exactly as quoted — this is the spelling-lock for
every baked string above.

=== LAYOUT GRID (fixed, landscape {ASPECT_RATIO}) ===
HEADER BAND (top 0-12%): solid {prim} band carrying the {client_name} wordmark, small,
top-left, in white; a thin {acc} rule at the band's bottom edge.
HERO BAND (12-30%): on {base}. The headline sits centered, the subheadline directly
beneath it in the {sec}-accented weight. Generous negative space around both; nothing
else competes with them in this band.
VIDEO-PLAYER BAND (30-80%): the single dominant element of the page — a large, centered,
rounded-rectangle video-player mockup on a soft {ink}-tinted frame, with a clean circular
PLAY glyph centered inside it (a simple triangle-in-circle, {prim} fill, white triangle,
no other iconography), and a thin progress-bar mockup along its bottom edge suggesting a
long-form video is waiting to be watched. No literal photograph of people is specified —
see the DO-NOT BLOCK anatomical-artifacts rule below.
CTA BAND (80-100%): the solid {prim} call-to-action button, centered beneath the
video-player mockup, with the CTA label in white, large enough to read at a glance; a
hairline {sec} rule above the band.
Safe margins 0.5in-equivalent on all sides; nothing touches the edges.

=== CONTENT ZONE PLACEMENT ===
On a strict horizontal grid: the HEADER band anchors identity, the HERO band carries the
headline+subheadline pair as the first focal point (largest type on the page, highest
contrast against {base}), the VIDEO-PLAYER band is the single largest visual element on
the page (the eye's ultimate destination — the player mockup, not the type, is the
biggest shape here), and the CTA band closes with one unmissable button beneath it. The
bands and their relative heights read as one designed system with the department's other
upsell pages (sales/checkout), sharing the SAME brand lockup, palette and typography
ladder, so a visitor arriving from either surface recognizes the same brand.

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
   VSL page" meta text, no design-brief fragment leaking onto the canvas.
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
Vertical-thirds grid; the video-player mockup is the hero shape; reading order = header
wordmark -> headline -> subheadline -> video-player mockup with PLAY glyph -> CTA button.
Brand hex: {prim}, {sec}, {acc}, {base}, {ink}. Headline 48-64pt BLACK, subheadline 22-28pt
ExtraBold, CTA label 18-22pt Bold. 8th-row readability: the headline, the PLAY glyph and
the CTA button must still read when the page is shrunk to 25%. The video-player mockup
must be the single highest-contrast, largest shape on the page.

=== VIDEO-PLAYER MOCKUP DETAIL ===
The video-player mockup is a designed UI element, not a photograph and not a literal
screen-capture of any real application: a rounded-rectangle frame in a deep {ink}-tinted
near-black fill, a subtle inner border in {acc} at low opacity, and a soft drop shadow
lifting it off the {base} page background. Inside the frame: the single circular PLAY
glyph is dead-center, large enough to read as the page's second-highest-contrast element
after the CTA button (the video-player band's own highest-contrast element). Beneath the
glyph, a thin horizontal progress-bar mockup spans roughly 80% of the frame's width near
the bottom edge, a muted {sec}-toned track with a short {prim}-filled leading segment
suggesting the video is cued up and ready, not mid-play and not finished. Do not render
any timestamp digits, any volume icon, any fullscreen icon, or any other player chrome
beyond the PLAY glyph and the single progress-bar mockup described here — the frame stays
clean and uncluttered so it reads instantly as "press play" at a glance, even at 25% scale.
No screen content is depicted inside the frame beyond this described chrome; the frame
itself, not an imagined video still, is what carries the invitation to watch.

=== MOBILE CROP GUIDANCE ===
This same {ASPECT_RATIO} landscape composition must also read cleanly when center-cropped
to a taller mobile aspect: keep the headline, subheadline, video-player mockup and CTA
button horizontally centered within the middle 70% of the frame width, and keep all four
elements (headline, subheadline, video-player mockup, CTA button) vertically stacked in
that same top-to-bottom reading order, each legible on its own without depending on being
seen alongside the others. Nothing essential to the page's meaning may sit in the outer
15% margins on either side, since a mobile crop trims those margins first.

=== QUALITY ===
Crisp {RESOLUTION} edges, flat clean editorial-conversion aesthetic, professional VSL
landing-page design, high information density of DESIGN (brand + hierarchy), soft even
tone, uniform lighting, no competing visual firsts, no crop, no letterbox. The page reads
as a premium, finished marketing surface — not a blank shell, not an unfinished mockup.

=== DETERMINISTIC VARIANT ===
This is a single-page VSL hero, the third surface in the department's optional upsell set
(sales + checkout + VSL), sharing one brand lockup with the other two when they exist:
identical header band, identical palette, identical typography ladder. Only the
headline/subheadline/CTA copy and the video-player-mockup emphasis are unique to this
page, so the full set reads as one designed system end to end.
"""
    return prompt


# ---------------------------------------------------------------------------
# HTML — body-level fragment (ghl_rest_canvas.html_fragment-compatible: no
# <!DOCTYPE>/<html>/<head>/<body> wrapper). Inline <style>/<script> are fine inside a
# bare fragment (mirrors sales_checkout_builder.py's build_page_html; lint_ghl_fragment
# explicitly allows inline <style>, confirmed render-surviving).
# ---------------------------------------------------------------------------
def build_vsl_html(*, brand: Dict[str, str], client_name: str, fields: Dict[str, str],
                   hero_image_src: Optional[str], video_src: str, video_hosted: bool,
                   gate_seconds: float, deck_slug: str, marker: str) -> str:
    prim, sec, acc, base, ink = (
        brand["primary"], brand["secondary"], brand["accent"], brand["base"], brand["ink"]
    )
    headline = fields.get("headline", "")
    subhead = fields.get("subhead", "")
    cta = fields.get("cta", "")
    hero_img_tag = (
        f'<img src="{hero_image_src}" alt="{client_name} VSL hero" '
        f'style="width:100%;max-width:100%;display:block;border-radius:12px;margin:0 0 24px;">'
        if hero_image_src else
        '<!-- hero image not yet hosted in GHL media (offline/no-push build) -->'
    )
    video_tag = (
        f'<video id="zhc-vsl-video-{deck_slug}" controls playsinline '
        f'style="width:100%;max-width:100%;display:block;border-radius:12px;background:#000;">'
        f'<source src="{video_src}" type="video/mp4"></video>'
        if video_hosted else
        f'<video id="zhc-vsl-video-{deck_slug}" controls playsinline '
        f'style="width:100%;max-width:100%;display:block;border-radius:12px;background:#000;">'
        f'<source src="{video_src}" type="video/mp4">'
        f'<!-- ZHC-VSL: local file reference, not yet GHL-hosted -- re-run P9.6 with its '
        f'upload step, or this src will not resolve once pushed. --></video>'
    )
    gate_id = f"zhc-vsl-gate-{deck_slug}"
    form_id = f"zhc-vsl-gate-form-{deck_slug}"
    return f"""<!-- ZHC-VSL-BUILDER marker={marker} deck_slug={deck_slug} -->
<style>
  .zhc-vsl-page {{ font-family: 'Montserrat', Arial, sans-serif; background:{base}; color:{ink}; padding:32px 24px; }}
  .zhc-vsl-page h1 {{ color:{ink}; font-size:2.4em; font-weight:800; margin:0 0 12px; text-align:center; }}
  .zhc-vsl-page h2 {{ color:{sec}; font-size:1.3em; font-weight:600; margin:0 0 24px; text-align:center; }}
  .zhc-vsl-page .cta-button {{ display:inline-block; background:{prim}; color:#fff; font-weight:700; padding:16px 32px; border-radius:8px; text-decoration:none; font-size:1.1em; margin-top:24px; }}
  .zhc-vsl-page .cta-row {{ text-align:center; }}
  .zhc-vsl-video-wrap {{ position:relative; max-width:900px; margin:0 auto; }}
  .zhc-vsl-gate-overlay {{ position:absolute; inset:0; background:rgba(0,0,0,.92); display:none; align-items:center; justify-content:center; z-index:50; border-radius:12px; }}
  .zhc-vsl-gate-overlay.zhc-vsl-gate-active {{ display:flex; }}
  .zhc-vsl-gate-form {{ background:{base}; border:1px solid {sec}; border-radius:10px; padding:24px; width:90%; max-width:360px; }}
  .zhc-vsl-gate-form h3 {{ color:{ink}; margin:0 0 16px; font-size:1.1em; }}
  .zhc-vsl-gate-form input {{ display:block; width:100%; box-sizing:border-box; margin:0 0 12px; padding:10px; border:1px solid {sec}; border-radius:6px; }}
  .zhc-vsl-gate-form button {{ display:block; width:100%; background:{prim}; color:#fff; font-weight:700; padding:12px; border:0; border-radius:6px; cursor:pointer; }}
</style>
<div class="zhc-vsl-page" id="zhc-vsl-{deck_slug}">
  {hero_img_tag}
  <h1>{headline}</h1>
  <h2>{subhead}</h2>
  <div class="zhc-vsl-video-wrap">
    {video_tag}
    <div class="zhc-vsl-gate-overlay" id="{gate_id}">
      <form class="zhc-vsl-gate-form" id="{form_id}">
        <h3>Enter your info to keep watching</h3>
        <input type="text" name="first_name" placeholder="First Name" required>
        <input type="email" name="email" placeholder="Email Address" required>
        <input type="tel" name="phone" placeholder="Cell Phone" required>
        <button type="submit">Continue Watching</button>
      </form>
    </div>
  </div>
  <div class="cta-row"><a class="cta-button" href="#">{cta}</a></div>
</div>
<script>
(function() {{
  var GATE_SEC = {gate_seconds};
  var video = document.getElementById('zhc-vsl-video-{deck_slug}');
  var overlay = document.getElementById('{gate_id}');
  var form = document.getElementById('{form_id}');
  var unlocked = false;
  if (video && overlay && form) {{
    video.addEventListener('timeupdate', function() {{
      if (!unlocked && video.currentTime >= GATE_SEC) {{
        video.pause();
        overlay.classList.add('zhc-vsl-gate-active');
      }}
    }});
    video.addEventListener('seeking', function() {{
      if (!unlocked && video.currentTime > GATE_SEC) {{
        video.currentTime = GATE_SEC;
      }}
    }});
    form.addEventListener('submit', function(ev) {{
      ev.preventDefault();
      /* ZHC-VSL: wire this submit to the client's real GHL contact-upsert endpoint or
         native GHL form embed at deployment time -- a fleet template does not carry a
         client's live endpoint. This gate mechanic (pause + seek-block + reveal-on-
         submit) is fully functional client-side; only the lead-delivery wiring is a
         deployment-time step, intentionally left unfabricated here. */
      unlocked = true;
      overlay.classList.remove('zhc-vsl-gate-active');
      video.play();
    }});
  }}
}})();
</script>
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
    prompts_path = renders_dir.parent / "vsl_prompts.json"
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
# browser_manager import at all -- mirrors sales_checkout_builder.py exactly).
# ---------------------------------------------------------------------------
def resolve_shared_funnel_id(run_dir: Path) -> Optional[str]:
    """Loop 2C's real, proven build put sales+checkout+VSL as THREE PAGES inside ONE
    funnel. When this run's sales_checkout_builder.py ledger already recorded a
    verified push (status == 'built+verified+pushed', a real funnel_id in its
    receipt), reuse that SAME funnel for the VSL page instead of creating a second
    one. Returns None when no such record exists (this run creates its own funnel,
    same as sales_checkout_builder.py does on a first run) -- never a hard failure."""
    ledger = _read_json(run_dir / "working" / "checkpoints" / "sales_checkout.json")
    if ledger.get("status") != "built+verified+pushed":
        return None
    receipt = ledger.get("receipt")
    if not isinstance(receipt, dict):
        return None
    fid = receipt.get("funnel_id")
    return str(fid).strip() if fid else None


def build_ghl_push_plan(*, location_id: str, funnel_name: str, deck_slug: str,
                        vsl_html: str, brand: Dict[str, str],
                        shared_funnel_id: Optional[str] = None) -> Dict[str, Any]:
    rc = _import_ghl_rest_canvas()

    vsl_slug = f"{deck_slug}-vsl"
    vsl_blob = rc.new_page_blob(
        vsl_html, surface="funnel",
        primary_color=brand.get("primary"), secondary_color=brand.get("secondary"),
    )

    sequence: List[Dict[str, Any]] = []
    step_no = 1
    if shared_funnel_id:
        note_prefix = (
            f"Reusing the sales/checkout funnel {shared_funnel_id!r} (Loop 2C's proven "
            "one-funnel/three-page layout) -- no funnel_create step needed."
        )
        funnel_id_placeholder = shared_funnel_id
    else:
        funnel_step = rc.funnel_create(location_id, funnel_name, funnel_type="funnel")
        sequence.append({
            "step": step_no,
            "call": "ghl_rest_canvas.funnel_create",
            "args": {"location_id": location_id, "name": funnel_name, "funnel_type": "funnel"},
            "precomputed_step": funnel_step,
            "then": "run the eval; parse response body.id -> FUNNEL_ID",
        })
        step_no += 1
        note_prefix = "No prior verified sales/checkout push found -- creating a new funnel."
        funnel_id_placeholder = "FUNNEL_ID"

    sequence.append({
        "step": step_no,
        "call": "ghl_rest_canvas.step_create",
        "args": {"funnel_id": funnel_id_placeholder, "name": f"{funnel_name} — VSL", "slug": vsl_slug},
        "then": "run the eval; created_page_id(response) -> VSL_PAGE_ID (new_page_version=1)",
    })
    step_no += 1
    sequence.append({
        "step": step_no,
        "call": "ghl_rest_canvas.page_autosave",
        "args": {"page_id": "VSL_PAGE_ID", "funnel_id": funnel_id_placeholder, "page_version": 1,
                "page_data": vsl_blob},
        "then": "run the eval; expect 201; live pointer unchanged (draft)",
    })

    return {
        "note": note_prefix + " " + (
            "Delegated GHL push plan -- ghl_rest_canvas.py's /funnels/* routes are "
            "Cloudflare-WAF-gated and MUST run inside a live agent-browser eval context "
            "(bare Python gets HTTP error 1010); this builder cannot drive a browser "
            "itself. An agent holding a seeded, activated, GHL-origin-navigated "
            "agent-browser session executes `sequence` below IN ORDER using the REAL "
            "ghl_rest_canvas.py functions named (never reimplemented), then writes "
            "working/vsl/build_receipt.json with the real resulting preview_urls + "
            "funnel_id + a QC score >= 8.5 (mirrors sales_checkout_builder.py's "
            "identical build_receipt contract). Re-running this builder after that "
            "receipt lands verifies it and reports PUSHED."
        ),
        "location_id": location_id,
        "funnel_name": funnel_name,
        "shared_funnel_id": shared_funnel_id,
        "sequence": sequence,
        "page_data": {"vsl": vsl_blob},
        "slugs": {"vsl": vsl_slug},
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
    """Mirrors sales_checkout_builder.py's _real_url exactly: an http(s) URL whose
    host is not a placeholder host or a subdomain of one."""
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
    NOT a failure -- mirrors sales_checkout_builder.py's identical contract)."""
    receipt_path = run_dir / "working" / "vsl" / "build_receipt.json"
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
# Front-door nonce (identical contract to workbook_builder.py / build_deck.py /
# build_webinar_video.py / sales_checkout_builder.py)
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
# Ledger (mirrors sales_checkout_builder.py's _record_ledger -- merged, never
# clobbered). Its own file, working/checkpoints/vsl.json -- NOT the shared
# sales_checkout.json this module only ever READS (resolve_shared_funnel_id).
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_ledger(run_dir: Path, record: dict) -> None:
    ledger = run_dir / "working" / "checkpoints" / "vsl.json"
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
        description="Build the VSL (video sales letter) page (kie.ai design -> copy -> "
                    "HTML+gate -> delegated GHL funnel push), gated on WANT_VSL_PAGE, "
                    "hard-gated on the P9.6 webinar video artifact."
    )
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--skip-design", action="store_true",
                    help="reuse working/vsl/renders/ PNGs; skip a fresh kie.ai run")
    ap.add_argument("--no-push", action="store_true",
                    help="offline smoke build: copy+design+HTML only, no nonce required, "
                         "no GHL push plan/receipt steps (the video dependency check "
                         "still runs)")
    ap.add_argument("--selftest", action="store_true", help="offline deterministic self-test")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.run_dir:
        ap.error("--run-dir is required (or --selftest)")
    run_dir = Path(args.run_dir).resolve()

    intake = load_intake(run_dir)

    # --- THE GATE ---
    gate = resolve_vsl_gate(intake)
    print(f"\n=== WANT_VSL_PAGE gate: {gate['decision'].upper()} ===")
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
    deck_slug = resolve_deck_slug(run_dir)

    # --- THE HARD VIDEO DEPENDENCY (must run after P9.6) ---
    try:
        video_path = verify_video_dependency(run_dir, deck_slug)
    except VslBuildError as exc:
        _record_ledger(run_dir, {"status": "video_missing", "gate": gate,
                                 "error": str(exc), "checked_at": _now_iso()})
        print(f"FATAL: {exc}", file=sys.stderr)
        return EXIT_VIDEO_MISSING
    print(f"\n=== P9.6 video dependency verified: {video_path} "
          f"({video_path.stat().st_size:,} bytes) ===")

    if not args.no_push:
        if not _verify_entry_nonce(run_dir):
            print(
                "FATAL [AF-CANONICAL-RENDER-BYPASS]: vsl_builder.py must run via "
                "presentation-canonical-entry.sh, which mints the per-run front-door "
                "nonce. Direct invocation is refused (a hand-rolled build cannot spend "
                "kie.ai money or touch a client's GHL funnel). Use --no-push ONLY for "
                "an operator offline smoke build (no client GHL write).",
                file=sys.stderr,
            )
            return EXIT_USAGE

    brand = resolve_brand(run_dir, intake)
    client_name = resolve_client_name(run_dir, intake)
    brief = resolve_brief(intake)

    vsl_dir = run_dir / "working" / "vsl"
    copy_dir = vsl_dir / "copy"
    renders_dir = vsl_dir / "renders"
    html_dir = vsl_dir / "html"
    for d in (copy_dir, renders_dir, html_dir):
        d.mkdir(parents=True, exist_ok=True)

    # --- COPY ---
    vsl_copy = build_vsl_copy(brief, client_name)
    (copy_dir / "vsl.md").write_text(vsl_copy, encoding="utf-8")
    print(f"\n=== Copy written -> {copy_dir}/vsl.md ===")

    # --- GATE TIMESTAMP (derived from THIS run's own webinar_timing.json) ---
    gate_ts = resolve_gate_timestamp(run_dir)
    print(f"\n=== VSL viewer gate: {gate_ts['seconds']}s ({gate_ts['source']}) ===")

    # --- DESIGN (kie.ai, unless --skip-design) ---
    fields = _vsl_content_fields(brief, client_name)
    prompt = build_design_prompt(brand=brand, client_name=client_name, fields=fields)
    assert_content_in_prompt("vsl-hero", fields, prompt)
    _assert_prompt_band(prompt, "vsl-hero")

    vsl_png = renders_dir / "vsl-hero.png"
    if args.skip_design:
        if not vsl_png.exists():
            print(f"FATAL: --skip-design but missing render: {vsl_png}", file=sys.stderr)
            return EXIT_USAGE
    else:
        prompts = [{"slide": "vsl-hero", "prompt": prompt, "mode": "t2i",
                   "aspect_ratio": ASPECT_RATIO, "resolution": RESOLUTION}]
        ok, detail = run_kie_generate(prompts, renders_dir)
        print(f"\n=== kie.ai design: {detail} ===")
        if not ok:
            _record_ledger(run_dir, {"status": "design_failed", "detail": detail, "built_at": _now_iso()})
            return EXIT_BUILD_FAILED

    # --- resolve the video's hosted GHL url (VSL-BUILDER-SOP.md §8 cross-check) ---
    video_url, video_warning = resolve_video_ghl_url(run_dir, deck_slug)
    if video_warning:
        print(f"WARNING: {video_warning}", file=sys.stderr)
    if video_url:
        video_src, video_hosted = video_url, True
    else:
        video_src, video_hosted = video_path.name, False

    # --- HOST the hero render (only when we intend to push) ---
    vsl_img_src = None
    if not args.no_push:
        try:
            ghl_media = _import_ghl_media()
            pit = ghl_media.resolve_location_pit()
            location_id = ghl_media.resolve_location_id()
            up_vsl = ghl_media.upload_media(str(vsl_png), location_id, vsl_png.name, pit,
                                            require_png=False, run_dir=run_dir)
            vsl_img_src = up_vsl["url"]
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: hero image GHL hosting failed ({exc}); HTML will be built "
                  "without a hosted hero image and the push plan step will fail its own "
                  "images-as-media-links gate until re-run.", file=sys.stderr)

    # --- HTML (with the gate) ---
    marker = f"ZHC-VSL-{deck_slug}"
    html = build_vsl_html(
        brand=brand, client_name=client_name, fields=fields, hero_image_src=vsl_img_src,
        video_src=video_src, video_hosted=video_hosted, gate_seconds=gate_ts["seconds"],
        deck_slug=deck_slug, marker=marker,
    )
    (html_dir / "vsl.html").write_text(html, encoding="utf-8")
    print(f"\n=== HTML written -> {html_dir}/vsl.html ===")

    missing = _html_content_strings_present(html, fields)
    if missing:
        print(f"FATAL: content strings missing from assembled HTML: {missing}", file=sys.stderr)
        _record_ledger(run_dir, {"status": "html_content_gate_failed", "built_at": _now_iso()})
        return EXIT_VERIFY_FAILED

    if not video_hosted and not args.no_push:
        print("WARNING: the P9.6 webinar video has no GHL ghl_url on record (P9.6 likely ran "
              "with --no-upload) -- the VSL page embeds a LOCAL file reference that will not "
              "resolve once pushed. Push proceeds (the video EXISTS -- that is the hard gate; "
              "hosting is a separate concern), but re-run P9.6 with its upload step before "
              "going live.", file=sys.stderr)

    record: Dict[str, Any] = {
        "deck_slug": deck_slug,
        "gate": gate,
        "video_path": str(video_path),
        "video_hosted": video_hosted,
        "gate_timestamp": gate_ts,
        "vsl_copy": str(copy_dir / "vsl.md"),
        "vsl_render": str(vsl_png),
        "vsl_html": str(html_dir / "vsl.html"),
        "built_at": _now_iso(),
    }

    if args.no_push:
        record["status"] = "built_offline_no_push"
        _record_ledger(run_dir, record)
        print("\nVSL BUILD (offline, --no-push): DONE")
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

    shared_funnel_id = resolve_shared_funnel_id(run_dir)
    try:
        plan = build_ghl_push_plan(
            location_id=location_id, funnel_name=f"{client_name} — VSL",
            deck_slug=deck_slug, vsl_html=html, brand=brand,
            shared_funnel_id=shared_funnel_id,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: GHL push plan construction failed: {exc}", file=sys.stderr)
        record["status"] = "push_plan_failed"
        record["error"] = str(exc)
        _record_ledger(run_dir, record)
        return EXIT_VERIFY_FAILED

    plan_path = vsl_dir / "ghl_push_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"\n=== GHL push plan written -> {plan_path} ===")
    print("Execute the plan's `sequence` inside a live agent-browser session, write "
          "working/vsl/build_receipt.json, then re-run this builder to verify.")

    status, detail, receipt_data = verify_push_receipt(run_dir)
    print(f"\n=== push receipt: {detail} ===")
    record["push_plan"] = str(plan_path)
    if status is True:
        record["status"] = "built+verified+pushed"
        record["receipt"] = receipt_data
        _record_ledger(run_dir, record)
        print("\nVSL BUILD: PUSHED")
        return EXIT_OK
    if status is False:
        record["status"] = "receipt_invalid"
        record["receipt_error"] = detail
        _record_ledger(run_dir, record)
        print(f"FATAL [AF-VSL-RECEIPT-INVALID]: {detail}", file=sys.stderr)
        return EXIT_VERIFY_FAILED

    record["status"] = "built+verified+plan_emitted"
    _record_ledger(run_dir, record)
    print("\nVSL BUILD: PLAN EMITTED (awaiting delegated agent-browser push)")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Offline deterministic self-test (no network, no kie.ai spend, no GHL call, no real
# video/audio -- every ghl_rest_canvas call below is made WITHOUT a session, which is
# pure/local by construction).
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    fails: List[str] = []

    # 1) THE GATE — every branch, matching upsell-questions.json's inverted-default
    #    waiver semantics for want_vsl_page.
    def _gate(pre: dict) -> dict:
        return resolve_vsl_gate({"pre_presentation_capture": pre})

    g = _gate({})
    if g["decision"] != "defer":
        fails.append(f"gate(absent) expected defer, got {g['decision']}")
    g = _gate({"WANT_VSL_PAGE": ""})
    if g["decision"] != "defer":
        fails.append(f"gate(blank) expected defer, got {g['decision']}")
    g = _gate({"WANT_VSL_PAGE": "yes"})
    if g["decision"] != "build":
        fails.append(f"gate(yes) expected build, got {g['decision']}")
    g = _gate({"WANT_VSL_PAGE": "YES"})
    if g["decision"] != "build":
        fails.append(f"gate(YES, case-insensitive) expected build, got {g['decision']}")
    g = _gate({"WANT_VSL_PAGE": "no"})
    if g["decision"] != "fail_closed" or AF_WAIVER_MISSING not in g["detail"]:
        fails.append(f"gate(no, no reason) expected fail_closed/{AF_WAIVER_MISSING}, got {g}")
    g = _gate({"WANT_VSL_PAGE": "no", "VSL_PAGE_DECLINED_REASON": "  "})
    if g["decision"] != "fail_closed":
        fails.append(f"gate(no, blank reason) expected fail_closed, got {g['decision']}")
    g = _gate({"WANT_VSL_PAGE": "no", "VSL_PAGE_DECLINED_REASON": "ok"})
    if g["decision"] != "fail_closed":
        fails.append(f"gate(no, 2-char reason) expected fail_closed (< {MIN_WAIVER_QUOTE_CHARS} chars), got {g['decision']}")
    g = _gate({"WANT_VSL_PAGE": "no",
              "VSL_PAGE_DECLINED_REASON": "We don't have a video yet and don't want one."})
    if g["decision"] != "waived" or g.get("quote") != "We don't have a video yet and don't want one.":
        fails.append(f"gate(no, real reason) expected waived with quote preserved, got {g}")
    g = _gate({"WANT_VSL_PAGE": "maybe"})
    if g["decision"] != "fail_closed" or AF_VALUE_UNRECOGNIZED not in g["detail"]:
        fails.append(f"gate(maybe) expected fail_closed/{AF_VALUE_UNRECOGNIZED}, got {g}")

    # 2) THE HARD VIDEO DEPENDENCY — missing / empty / bad-magic / valid, all offline.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        deck_slug = "acme-q1"
        # 2a) no file at all -> VslBuildError naming AF-VSL-NO-VIDEO.
        try:
            verify_video_dependency(rd, deck_slug)
            fails.append("verify_video_dependency: missing video did not raise")
        except VslBuildError as exc:
            if AF_NO_VIDEO not in str(exc):
                fails.append(f"missing-video error did not name {AF_NO_VIDEO}: {exc}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"missing-video raised the wrong exception type: {exc!r}")

        video_path = resolve_video_artifact(rd, deck_slug)
        video_path.parent.mkdir(parents=True, exist_ok=True)
        expected_name = f"{deck_slug}-WEBINAR.mp4"
        if video_path.name != expected_name:
            fails.append(f"resolve_video_artifact: expected filename {expected_name!r}, "
                        f"got {video_path.name!r} (must reuse build_webinar_video.py's "
                        "own WEBINAR_FILENAME_TEMPLATE)")

        # 2b) zero-byte file -> VslBuildError (fails ghl_media.verify_video()).
        video_path.write_bytes(b"")
        try:
            verify_video_dependency(rd, deck_slug)
            fails.append("verify_video_dependency: empty video did not raise")
        except VslBuildError as exc:
            if AF_NO_VIDEO not in str(exc):
                fails.append(f"empty-video error did not name {AF_NO_VIDEO}: {exc}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"empty-video raised the wrong exception type: {exc!r}")

        # 2c) non-empty but not a real mp4 (bad magic) -> VslBuildError.
        video_path.write_bytes(b"NOT AN MP4 FILE" * 100)
        try:
            verify_video_dependency(rd, deck_slug)
            fails.append("verify_video_dependency: bad-magic video did not raise")
        except VslBuildError as exc:
            if AF_NO_VIDEO not in str(exc):
                fails.append(f"bad-magic error did not name {AF_NO_VIDEO}: {exc}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"bad-magic raised the wrong exception type: {exc!r}")

        # 2d) a genuine minimal mp4 (ftyp box) -> PASSES, returns the path.
        _valid_mp4 = (b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42"
                     b"\x00\x00\x00\x08free")
        video_path.write_bytes(_valid_mp4)
        try:
            got = verify_video_dependency(rd, deck_slug)
            if got != video_path:
                fails.append(f"verify_video_dependency(valid): returned {got}, expected {video_path}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"verify_video_dependency: a genuine mp4 fixture was REJECTED: {exc}")

        # video-url resolution + deck_slug cross-check warning.
        ck = rd / "working" / "checkpoints"
        ck.mkdir(parents=True, exist_ok=True)
        (ck / "media_library.json").write_text(json.dumps({
            "webinar_mp4": {"ghl_url": "https://storage.googleapis.com/msgsndr/loc/x.mp4",
                            "deck_slug": deck_slug},
        }))
        url, warn = resolve_video_ghl_url(rd, deck_slug)
        if url != "https://storage.googleapis.com/msgsndr/loc/x.mp4" or warn is not None:
            fails.append(f"resolve_video_ghl_url(matching slug): got url={url!r} warn={warn!r}")
        url, warn = resolve_video_ghl_url(rd, "some-other-deck")
        if warn is None:
            fails.append("resolve_video_ghl_url: mismatched deck_slug did not warn")

    # 3) GATE TIMESTAMP — with/without a timing track, inside/outside the window.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        # no track at all -> window midpoint default.
        r = resolve_gate_timestamp(rd)
        if abs(r["seconds"] - (VSL_GATE_MIN_SEC + VSL_GATE_MAX_SEC) / 2.0) > 0.01:
            fails.append(f"resolve_gate_timestamp(no track): expected midpoint, got {r}")

        ck = rd / "working" / "checkpoints"
        ck.mkdir(parents=True, exist_ok=True)
        # a track with a slide boundary inside the window -> picks it.
        (ck / "webinar_timing.json").write_text(json.dumps({
            "total_audio_sec": 1200.0,
            "timing": [
                {"slide": 1, "audio_start": 0.0},
                {"slide": 2, "audio_start": 90.0},
                {"slide": 3, "audio_start": 300.0},
                {"slide": 4, "audio_start": 600.0},
            ],
        }))
        r = resolve_gate_timestamp(rd)
        if r["seconds"] != 300.0:
            fails.append(f"resolve_gate_timestamp(in-window boundary): expected 300.0, got {r}")

        # a track with NO boundary inside the window, but a known total -> clamped.
        (ck / "webinar_timing.json").write_text(json.dumps({
            "total_audio_sec": 60.0,
            "timing": [{"slide": 1, "audio_start": 0.0}],
        }))
        r = resolve_gate_timestamp(rd)
        if not (VSL_GATE_MIN_SEC <= r["seconds"] <= VSL_GATE_MAX_SEC + 0.01):
            fails.append(f"resolve_gate_timestamp(short talk): {r['seconds']} landed outside "
                        f"[{VSL_GATE_MIN_SEC}, {VSL_GATE_MAX_SEC}]")

    # 4) COPY — deterministic, content present.
    brief = {
        "OFFER_NAME": "The Momentum Method",
        "TRANSFORMATION_PROMISE": "Go from stuck to shipped in 30 days.",
        "AUDIENCE": "overwhelmed solo founders",
        "CTA_ACTION": "Watch The Full Training",
        "PRIMARY_OBJECTION": "I don't have time for another program.",
        "PROOF_ASSETS": "312 founders shipped their first launch.",
        "HOOK_SEED": "You don't need more time. You need momentum.",
        "BRAND_PRIMARY": "#1a2b6d",
    }
    vsl_md = build_vsl_copy(brief, "Test Client")
    if brief["HOOK_SEED"] not in vsl_md or brief["OFFER_NAME"] not in vsl_md:
        fails.append("vsl copy missing baked content strings")

    # 5) DESIGN PROMPT — band + content-gate pass, adversarial fails.
    brand = resolve_brand(Path("/nonexistent"), {"deck_brief": brief})
    fields = _vsl_content_fields(brief, "Test Client")
    prompt = build_design_prompt(brand=brand, client_name="Test Client", fields=fields)
    n = len(prompt.strip())
    if not (PROMPT_FLOOR <= n <= PROMPT_CEILING):
        fails.append(f"vsl-hero: prompt {n} chars outside {PROMPT_FLOOR}-{PROMPT_CEILING} band")
    try:
        assert_content_in_prompt("vsl-hero", fields, prompt)
    except Exception as exc:  # noqa: BLE001
        fails.append(f"vsl-hero: content gate REJECTED a content-bearing prompt: {exc}")
    try:
        _assert_prompt_band(prompt, "vsl-hero")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"vsl-hero: band assertion failed on a valid prompt: {exc}")

    # 5b) adversarial: zero-content page MUST be refused.
    try:
        assert_content_in_prompt("adv-empty", {}, "DESIGN A LANDING PAGE BACKGROUND...")
        fails.append("content gate ACCEPTED a page with ZERO content strings")
    except RuntimeError as exc:
        if AF_PROMPT_NO_CONTENT not in str(exc):
            fails.append(f"zero-content rejection did not name the AF code: {exc}")
    # 5c) adversarial: wireframe directive present, even WITH content, MUST be refused.
    try:
        assert_content_in_prompt("adv-wire", fields,
                                 "This is the BACKGROUND ONLY for a landing page. NO text.")
        fails.append("content gate ACCEPTED a prompt carrying the BACKGROUND ONLY wireframe directive")
    except RuntimeError as exc:
        if AF_PROMPT_NO_CONTENT not in str(exc):
            fails.append(f"wireframe rejection did not name the AF code: {exc}")

    # 6) HTML — content strings present, ghl_rest_canvas.html_fragment compatible,
    #    the gate JS/overlay markup is present, and (when importable) new_page_blob /
    #    funnel_create / step_create / page_autosave / build_ghl_push_plan all work
    #    purely offline.
    marker = "ZHC-VSL-selftest"
    html = build_vsl_html(
        brand=brand, client_name="Test Client", fields=fields, hero_image_src=None,
        video_src="test-client-WEBINAR.mp4", video_hosted=False, gate_seconds=300.0,
        deck_slug="test-client", marker=marker,
    )
    missing = _html_content_strings_present(html, fields)
    if missing:
        fails.append(f"vsl HTML missing content strings: {missing}")
    for needle in ("zhc-vsl-gate-overlay", "timeupdate", "GATE_SEC = 300.0", "<video"):
        if needle not in html:
            fails.append(f"vsl HTML missing expected gate mechanic marker: {needle!r}")

    try:
        rc = _import_ghl_rest_canvas()
    except Exception as exc:  # noqa: BLE001
        fails.append(f"could not import ghl_rest_canvas.py: {exc}")
        rc = None

    if rc is not None:
        # bare fragment passthrough (no full-document wrapper) must be a no-op.
        try:
            frag = rc.html_fragment(html)
            if frag.strip() != html.strip():
                fails.append("html_fragment() mutated a bare body-level fragment (should be a no-op)")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"html_fragment() raised on a valid bare fragment: {exc}")

        # new_page_blob() — pure, offline, must succeed and internally pass
        # assert_renderable_shape (raises AssertionError otherwise).
        blob = None
        try:
            blob = rc.new_page_blob(html, surface="funnel",
                                    primary_color=brand["primary"], secondary_color=brand["secondary"])
            if not isinstance(blob, dict) or not blob.get("sections"):
                fails.append("new_page_blob() returned an unexpected shape")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"new_page_blob() raised on a valid fragment: {exc}")

        # funnel_create/step_create/page_autosave WITHOUT session -- pure/local,
        # no browser_manager import, no network call of any kind.
        try:
            fc = rc.funnel_create("loc123", "Test Client — VSL", funnel_type="funnel")
            if fc.get("method") != "POST" or "argv" in fc:
                fails.append(f"funnel_create() without session produced an unexpected step: {fc.keys()}")
            sc = rc.step_create("FUNNEL_ID", "VSL", "test-client-vsl")
            if sc.get("method") != "POST" or "argv" in sc:
                fails.append(f"step_create() without session produced an unexpected step: {sc.keys()}")
            if blob is not None:
                pa = rc.page_autosave("VSL_PAGE_ID", blob, funnel_id="FUNNEL_ID", page_version=1)
                if pa.get("method") != "POST" or "argv" in pa or pa["body"]["pageVersion"] != 2:
                    fails.append(f"page_autosave() without session produced an unexpected step: {pa}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"offline ghl_rest_canvas step construction raised: {exc}")

        # build_ghl_push_plan — BOTH branches (own funnel vs shared funnel), pure/offline.
        try:
            plan_own = build_ghl_push_plan(
                location_id="loc123", funnel_name="Test Client — VSL",
                deck_slug="test-client", vsl_html=html, brand=brand, shared_funnel_id=None,
            )
            if len(plan_own.get("sequence", [])) != 3:
                fails.append(f"build_ghl_push_plan(no shared funnel): expected 3 steps, "
                            f"got {len(plan_own.get('sequence', []))}")
            if plan_own["sequence"][0]["call"] != "ghl_rest_canvas.funnel_create":
                fails.append("build_ghl_push_plan(no shared funnel): step 1 is not funnel_create")

            plan_shared = build_ghl_push_plan(
                location_id="loc123", funnel_name="Test Client — VSL",
                deck_slug="test-client", vsl_html=html, brand=brand,
                shared_funnel_id="z20T0shared",
            )
            if len(plan_shared.get("sequence", [])) != 2:
                fails.append(f"build_ghl_push_plan(shared funnel): expected 2 steps, "
                            f"got {len(plan_shared.get('sequence', []))}")
            if plan_shared["sequence"][0]["call"] != "ghl_rest_canvas.step_create":
                fails.append("build_ghl_push_plan(shared funnel): step 1 is not step_create "
                            "(funnel_create should have been skipped)")
            if plan_shared["sequence"][0]["args"]["funnel_id"] != "z20T0shared":
                fails.append("build_ghl_push_plan(shared funnel): did not reuse the shared funnel_id")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"build_ghl_push_plan() raised on valid input: {exc}")

    # 7) resolve_shared_funnel_id — absent / not-yet-pushed / verified-pushed.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        if resolve_shared_funnel_id(rd) is not None:
            fails.append("resolve_shared_funnel_id(no ledger): expected None")
        ck = rd / "working" / "checkpoints"
        ck.mkdir(parents=True)
        (ck / "sales_checkout.json").write_text(json.dumps({"status": "built+verified+plan_emitted"}))
        if resolve_shared_funnel_id(rd) is not None:
            fails.append("resolve_shared_funnel_id(plan_emitted, not pushed): expected None")
        (ck / "sales_checkout.json").write_text(json.dumps({
            "status": "built+verified+pushed", "receipt": {"funnel_id": "z20T0real"},
        }))
        if resolve_shared_funnel_id(rd) != "z20T0real":
            fails.append(f"resolve_shared_funnel_id(pushed): expected 'z20T0real', "
                        f"got {resolve_shared_funnel_id(rd)!r}")

    # 8) receipt verification — absent / placeholder / real.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        status, detail, _ = verify_push_receipt(rd)
        if status is not None:
            fails.append(f"verify_push_receipt(absent) expected None (not-yet-executed), got {status}")

        vsl_dir = rd / "working" / "vsl"
        vsl_dir.mkdir(parents=True)
        (vsl_dir / "build_receipt.json").write_text(json.dumps({
            "preview_urls": ["https://example.com/preview/abc"],
            "funnel_id": "f1",
        }))
        status, detail, _ = verify_push_receipt(rd)
        if status is not False:
            fails.append(f"verify_push_receipt(placeholder host) expected False, got {status}")

        (vsl_dir / "build_receipt.json").write_text(json.dumps({
            "preview_urls": ["https://app.convertandflow.com/preview/abc123"],
            "funnel_id": "z20T0real",
        }))
        status, detail, _ = verify_push_receipt(rd)
        if status is not True:
            fails.append(f"verify_push_receipt(real) expected True, got {status} ({detail})")

        # 9) ledger round-trip.
        _record_ledger(rd, {"status": "built+verified+pushed", "a": 1})
        _record_ledger(rd, {"b": 2})
        ledger = json.loads((rd / "working" / "checkpoints" / "vsl.json").read_text())
        if ledger.get("a") != 1 or ledger.get("b") != 2:
            fails.append(f"ledger round-trip lost a field: {ledger}")

    # 10) front-door nonce — no env var, wrong env var, matching pair.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        if _verify_entry_nonce(rd):
            fails.append("_verify_entry_nonce: no env/file present but returned True")
        nf = rd / ENTRY_NONCE_REL
        nf.parent.mkdir(parents=True, exist_ok=True)
        nf.write_text("a-real-nonce-value-1234567890")
        old = os.environ.get("OC_DECK_ENTRY_NONCE")
        try:
            os.environ["OC_DECK_ENTRY_NONCE"] = "a-real-nonce-value-1234567890"
            if not _verify_entry_nonce(rd):
                fails.append("_verify_entry_nonce: matching env+file returned False")
            os.environ["OC_DECK_ENTRY_NONCE"] = "a-DIFFERENT-nonce-value-000000"
            if _verify_entry_nonce(rd):
                fails.append("_verify_entry_nonce: mismatched env+file returned True")
        finally:
            if old is None:
                os.environ.pop("OC_DECK_ENTRY_NONCE", None)
            else:
                os.environ["OC_DECK_ENTRY_NONCE"] = old

    if fails:
        print("vsl_builder selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("vsl_builder selftest -> PASS "
          "(gate: defer/build/waived/fail_closed x2 + case-insensitive; hard video "
          "dependency: missing/empty/bad-magic/valid + url cross-check; gate timestamp: "
          "no-track/in-window/short-talk; copy content; prompt band + content-gate "
          "pass/zero-content-refuse/wireframe-refuse; HTML content + gate markup + "
          "ghl_rest_canvas.html_fragment/new_page_blob/funnel_create/step_create/"
          "page_autosave (all offline, no session); push plan own-funnel/shared-funnel "
          "branches; shared-funnel-id resolution; receipt absent/placeholder/real; "
          "ledger round-trip; front-door nonce absent/mismatch/match)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
