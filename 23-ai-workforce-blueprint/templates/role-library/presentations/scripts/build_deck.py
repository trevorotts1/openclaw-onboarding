#!/usr/bin/env python3
# =============================================================================
# SOP-LOCKED DEPARTMENT: if you add/modify any SOP, role, or gate, you MUST
# update PIPELINE-MANIFEST.json + build_deck.py + a test. Run
# scripts/sync_check.py — it fails the gate if the Python and the SOP stack
# drift. The PREFLIGHT_REQUIRED set + the _chk_* checkers + every AF-* code this
# file cites are reconciled against
# universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json by
# scripts/sync_check.py (in BOTH directions). Procedure:
# universal-sops/presentation-slide-craft/SOP-SLIDE-06-EXTENSION-AND-SYNC.md.
# =============================================================================
"""
build_deck.py — DETERMINISTIC, NO-AI deck builder for the Presentations department.

================================================================================
A .pptx IS NOT A DELIVERED PRESENTATION. THIS SCRIPT IS ONLY THE PHASE-4 RENDERER.
================================================================================
Producing only a .pptx with this script is NOT a delivered presentation and is NOT
a complete deliverable. build_deck.py renders slide images and assembles a bare
.pptx — and NOTHING ELSE. It does NOT produce the presenter guide PDF, the presenter
speech (PRESENTERS-SPEECH.md/.pdf/-FISH-TAGGED.md), the presenter audio
(PRESENTER-AUDIO.mp3), the teleprompter app, the deck PDF export, the infographic
checklist slide, or the GHL media upload. The FULL deliverable downstream is the
NINE-MEMBER bundle —
    [Deck-Title]-FINAL.pptx, [Deck-Title]-FINAL.pdf, PRESENTER-GUIDE.pdf,
    PRESENTERS-SPEECH.md (pure), PRESENTERS-SPEECH.pdf (teleprompter PDF),
    PRESENTERS-SPEECH-FISH-TAGGED.md (fish-tagged), PRESENTER-AUDIO.mp3,
    infographic.png, presenter-teleprompter.html (the teleprompter web app).
The .pptx this script emits is an INTERMEDIATE artifact. The Director/Delivery flow
MUST run the guide / speech / audio / PDF / infographic / teleprompter roles, and the
run is blocked from "Done" by the POSTFLIGHT COMPLETENESS GATE (AF-BUNDLE-COMPLETE)
AND the DELIVERY INTERLOCK (AF-DELIVER + AF-DH1 + AF-DELIVERY-COMPLETE). Do NOT
"finish at a .pptx." See sops/CLIENT-WEBINAR-DECK-SOP.md §9a,
sops/delivery-concierge-sops.md SOP 9.5, and
sops/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md (AF-DELIVERY-COMPLETE).

UPSTREAM STEPS THAT PRODUCE THE REQUIRED OUTPUTS:
    - [Deck-Title]-FINAL.pdf            : produced by PPTX Assembly Specialist (PDF export)
    - PRESENTER-GUIDE.pdf               : produced by Presenters Guide Specialist
    - PRESENTERS-SPEECH.md/.pdf         : produced by Presenters Speech Writer
    - PRESENTERS-SPEECH-FISH-TAGGED.md  : produced by Presenters Speech Writer / Fish Audio
    - PRESENTER-AUDIO.mp3               : produced by Audio Demonstration Specialist
    - infographic.png                   : produced by infographic-checklist role
    - presenter-teleprompter.html       : produced by build_teleprompter.py (teleprompter role)
The postflight gate enforces that ALL NINE exist and pass their size thresholds. It
hard-fails (AF-BUNDLE-COMPLETE, exit 5) if any are missing or under-size, so they
can NEVER be silently skipped.

DEFAULT OUTPUT DESTINATION — ~/Downloads:
    The final bundle dir defaults to ~/Downloads/<client-slug>-<deck-slug>/.
    Use --out <dir> to override. Files NEVER default to a scratch/run dir — they
    go to ~/Downloads so the client receives them from a predictable, clean location.
================================================================================

This is the PROVEN deterministic deck pipeline, generalized for the fleet. It is the
single-command, zero-AI-at-runtime path that takes a slides.json (the agent's only
creative output) and produces a finished .pptx with no further model judgement.

WHAT IT DOES (zero AI judgement at runtime):
    1. Reads a slides.json (see slides.schema.json) and an output .pptx path.
    2. For EACH slide, LOADS the per-slide RICH prompt VERBATIM from
         working/prompts/slide-NN.txt  (or the SOP-named  slide-NN-prompt.txt).
       This is the Slide Image Creator's hand-authored output — a 1,500–18,000-char
       prompt that already carries the typography (per-line weight + pt size),
       placement, usage, the logo(s), the scene, the verbatim copy, the negative
       block, and everything else that appears on the slide. build_deck.py renders
       THAT prompt verbatim — it does NOT compose its own thin prompt from
       scene+copy. A whole slide is rendered in ONE gpt-image-2 generation.
       If a slide has NO rich prompt file, or the prompt is < PROMPT_CHAR_FLOOR
       (1,500) chars, build_deck.py FAILS LOUD — it NEVER silently falls back to a
       thin composed prompt. TWO prompt-side QC gates run on every rich prompt,
       both FAIL-LOUD (no silent render):
         (a) FACIAL-INTELLIGENCE / REPRESENTATION gate — refuses any prompt that
             carries a forbidden hardcoded demographic default (the "60/30/10"
             landmine). Representation comes from the slide spec / casting ledger
             (the client's captured audience), never a baked-in default split
             (SOP-CAST-01, AF-R3).
         (b) CHAR-COUNT gate — the rich prompt length must be within
             [PROMPT_CHAR_FLOOR, PROMPT_CHAR_CEILING] = [1500, 18000]; the floor is
             HARD (any prompt under 1,500 chars is not run, not rendered, not
             updated — AF-P1) and the 18,000 ceiling is the universal GPT-Image 2
             safety boundary (AF-P2).
    3. Calls KIE.ai (gpt-image-2-text-to-image, or gpt-image-2-image-to-image when a
       logo is supplied via input_urls so the WHOLE slide + logo render in ONE
       generation) per the ONLY-allowed recipe:
         POST https://api.kie.ai/api/v1/jobs/createTask  -> data.taskId
         GET  https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>  -> data.state
         on success: parse data.resultJson (JSON string) -> resultUrls[0]
       Poll every ~8s up to ~7 minutes. Heavy gpt-image-2 renders (split scenes,
       multiple photoreal zones) routinely run past 3 minutes; a slide that is still
       actively 'generating' is given the full ceiling (plus a bounded grace window)
       before it is declared a timeout. On HTTP 429, sleep 20s and retry.
    4. Downloads resultUrls[0] UNAUTHENTICATED to <renders_dir>/slide-NN.png.
    5. VERIFIES each PNG: real PNG magic bytes AND non-zero size.
    6. Retries a failing slide up to 3 times (re-submit from scratch).
    7. Assembles ALL slide PNGs into a 16:9 .pptx via python-pptx — ONE full-bleed
       picture per slide, NO text boxes (text is baked into the KIE image, matching the
       designed architecture).
    8. Prints a JSON summary: {slidesRendered, kieTaskIds, outputPath, failures}.

HARD CONTRACTS:
    * It NEVER calls any native/built-in image tool (image_generate, openai, etc.).
      KIE createTask is the ONLY image path.
    * The dead endpoint /api/v1/image/gpt-image is NEVER used (and is refused if seen).
    * If KIE is unreachable / a slide cannot be rendered after retries, the script FAILS
      LOUDLY with a non-zero exit code. It NEVER silently substitutes a placeholder image.

USAGE:
    python3 build_deck.py <slides.json> <out.pptx> [renders_dir] [--run-dir DIR]
        [--logo PNG] [--out BUNDLE_DIR] [--adhoc-no-process]

    renders_dir defaults to "<out.pptx dir>/renders".
    --out BUNDLE_DIR  overrides the default ~/Downloads/<client-slug>-<deck-slug>/
                      destination for the final deliverable bundle. If not supplied,
                      the bundle goes to ~/Downloads.

    NOTE: a successful run (exit 0 + a .pptx at <out.pptx>) means the deck is
    RENDERED, not DELIVERED. The .pptx alone is NOT a delivered presentation — the
    full nine-member bundle (deck .pptx/.pdf, guide PDF, the three speech artifacts,
    audio, infographic, teleprompter app) is required downstream (see the banner
    above and the POSTFLIGHT COMPLETENESS GATE / DELIVERY INTERLOCK).

OFFICIAL-LOGO COMPOSITING (optional):
    --logo <png-or-URL>  — the client's REAL, official logo. When supplied
        (or when working/copy/intake.json carries brand.logo_image_path), the deck
        wears the client's actual mark, not an AI-hallucinated wordmark:
          (1) When --logo is a URL: KIE composites the REAL logo via image-to-image
              (gpt-image-2-image-to-image, input_urls) in the SAME single generation
              that renders the slide — the rich prompt already carries the
              "place this exact provided logo, do not redraw/recolor/restyle"
              instruction (the AI wordmark is suppressed by the prompt itself).
          (2) When --logo is a local PNG: assemble_pptx composites the EXACT same
              logo PNG (RGBA, transparency preserved) onto EVERY slide in a
              consistent top-right corner at a tasteful size (~13% of slide width)
              with a small margin, layered over the full-bleed background.
        The --logo flag wins over intake.json brand.logo_image_path if both exist.
        Either way the prompt is the rich verbatim prompt — build_deck.py never
        rewrites the logo instruction; the Slide Image Creator authored it.

PROCESS PREFLIGHT (un-bypassable by default):
    Before ANY render or assembly, build_deck.py REQUIRES that the upstream
    department process artifacts already exist on disk in the run/working dir.
    build_deck.py is ONLY the deterministic Phase-4 renderer + a stripped Phase-8
    assembler; it carries none of the upstream intelligence (research, copy,
    human approvals) or QC gates. Running it on a hand-fed slides.json with no
    upstream chain produces a technically-valid .pptx that NEVER went through the
    department flow — exactly the shortcut this preflight exists to refuse.

    The preflight enforces EVERY SOP artifact: intake, research brief, converting
    arc, slides_copy, design/typography brief, copy QC (pass), anti-compression
    coverage, AND a >=1,500-char RICH prompt for EVERY slide in working/prompts/
    (the Slide Image Creator's output). Any missing/short/deviation → refuse to
    render, exit 3, loud. There is no path past the gate with a thin or absent
    per-slide prompt.

    The run dir is the directory that contains a `working/` subtree. It is found
    by --run-dir if given, else by walking UP from slides.json (then from the
    out.pptx dir) until a `working/` dir is found, else slides.json's parent.

    Required artifacts (each annotated with the dept phase/role that produces it)
    are listed in PREFLIGHT_REQUIRED below. If ANY is missing or incomplete, the
    script FAILS LOUD (exit 3), prints exactly which artifacts are missing and who
    produces each, and renders/assembles NOTHING.

    --adhoc-no-process  — DELIBERATE standalone-testing override ONLY. Skips the
        process preflight, prints a loud banner that the output is NOT a
        process-compliant deliverable, and proceeds. NEVER use for client work.

EXIT CODES:
    0 — every slide rendered, the .pptx was written, AND the postflight
        completeness gate confirmed all nine bundle deliverables present + sized.
    1 — one or more slides failed after retries (NO .pptx written), or assembly failed.
    2 — fatal config error (no API key, bad slides.json, missing python-pptx, etc.).
    3 — process preflight FAILED: required upstream dept artifacts are missing
        (NO render, NO .pptx). Run the real dept pipeline, or pass
        --adhoc-no-process for explicit non-deliverable standalone testing.
    5 — POSTFLIGHT COMPLETENESS GATE FAILED (AF-BUNDLE-COMPLETE): one or more
        required deliverables are missing or below their size threshold. The run
        may NOT be reported as "done" / "complete" until exit 0. The .pptx was
        written but the bundle is incomplete.

ENVIRONMENT:
    KIE_API_KEY — the CLIENT's own KIE.ai key (never the operator's, never shared).
    Read from env, else from one of the client's standard env stores:
        ~/.openclaw/workspace/.env
        ~/clawd/secrets/.env
        ~/.openclaw/secrets/.env
    (paths expanded against the current user's HOME).
"""

import concurrent.futures
import hashlib
import ipaddress
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Constants — the ONLY allowed KIE.ai endpoints/model (verified live 2026-06-16)
# ---------------------------------------------------------------------------

CREATE_URL = "https://api.kie.ai/api/v1/jobs/createTask"
POLL_URL   = "https://api.kie.ai/api/v1/jobs/recordInfo"
MODEL_T2I  = "gpt-image-2-text-to-image"
MODEL_I2I  = "gpt-image-2-image-to-image"  # OFFICIAL-LOGO mode: KIE composites the REAL logo via input_urls (image-to-image), NOT a flat overlay or AI wordmark

ASPECT_RATIO = "16:9"
RESOLUTION   = "2K"

# ---------------------------------------------------------------------------
# OFFICIAL-LOGO compositing geometry (used by assemble_pptx)
# ---------------------------------------------------------------------------
# Slide is 16:9 at 10" x 5.625". The real logo is composited top-right at a
# tasteful size: ~13% of slide width, with a small consistent margin. The logo's
# native aspect ratio is preserved (height derived from its pixel dimensions) so
# the EXACT client file is never distorted; transparency (RGBA) is preserved
# because python-pptx passes PNG alpha straight through.
SLIDE_WIDTH_IN  = 10.0
SLIDE_HEIGHT_IN = 5.625
LOGO_WIDTH_FRACTION = 0.13   # ~13% of slide width (within the 12-15% tasteful band)
LOGO_MARGIN_IN = 0.25        # small consistent margin from the top/right edges

# DEAD endpoint — refuse to ever touch it.
DEAD_ENDPOINT_FRAGMENT = "/api/v1/image/gpt-image"

# Poll cadence per the recipe: ~8s interval, up to ~7 minutes total.
# Heavy gpt-image-2 renders (e.g. a split then-vs-now band with two photoreal scenes
# and multiple text zones) regularly exceed 3 minutes of pure render latency. 180s was
# too low and made merely-slow slides time out and fail loud with outputPath=null. 420s
# gives slow-but-healthy renders room to finish; genuine terminal failures still fail
# immediately (see poll_task: 'fail'/'error'/'cancelled' short-circuit).
POLL_INTERVAL_S = 8
POLL_MAX_SECONDS = 420
POLL_MAX_PASSES = POLL_MAX_SECONDS // POLL_INTERVAL_S  # ~52 passes

# 429 backoff.
RATE_LIMIT_SLEEP_S = 20

# Per-slide retries (full re-submit) on any failure.
SLIDE_MAX_ATTEMPTS = 3

# Parallel render fan-out. Each slide is an independent KIE generation (submit +
# poll + download + verify), so they run concurrently in a ThreadPoolExecutor.
# Bounded so the per-task 429 backoff still holds and a client box is not swamped.
# Overridable via BUILD_DECK_RENDER_WORKERS (clamped to [1, 12]).
def _render_workers() -> int:
    try:
        n = int(os.environ.get("BUILD_DECK_RENDER_WORKERS", "6"))
    except ValueError:
        n = 6
    return max(1, min(12, n))

# The MANDATORY trailing pin appended to EVERY prompt.
ENGLISH_PIN = (
    "All text rendered in the image MUST be in English, Latin alphabet ONLY. "
    "NO Chinese/CJK or non-Latin characters anywhere. Render the copy spelled "
    "correctly, letter-for-letter. No garbled, misspelled, or invented text."
)

# ---------------------------------------------------------------------------
# PROMPT CHAR-COUNT GATE (the prompt-side QC gate, fail-loud)
# ---------------------------------------------------------------------------
# Two facts from the standards (qc-specialist-presentations.md AF-P1/AF-P2,
# slide-image-creator-sops.md SOP 9.1 step 3, MODEL-SPECS.md):
#   * GPT-Image 2 hard ceiling on input.prompt is 20,000 characters on both
#     endpoints. The HARD MAXIMUM is 18,000 — a 2,000-char safety margin below
#     that ceiling so a prompt is never rejected or truncated by the platform.
#     This ceiling is UNIVERSAL: it applies to every prompt path. A prompt over
#     it is an AF-P2 auto-fail.
#   * The FLOOR is 1,500 chars and it is HARD (AF-P1). build_deck.py does NOT
#     compose its own thin prompt any more — it renders the Slide Image Creator's
#     hand-authored RICH per-slide prompt VERBATIM (working/prompts/slide-NN.txt).
#     That prompt carries the full 15-element spec (typography size + per-line
#     weight, placement, usage, the logo(s), the scene, verbatim copy, the negative
#     block, everything on the slide); the SOP targets 9,000–14,000 chars. A prompt
#     under 1,500 chars is, by definition, not a real slide prompt — it is a thin
#     stub or a truncated file — so it is NOT run, NOT rendered, and NOT updated:
#     the slide FAILS LOUD (AF-P1). 1,500 is the absolute minimum below which a
#     prompt cannot possibly carry the mandatory specificity; the SOP's own
#     soft-minimum of 5,000 lives upstream at the Slide Image Creator / Phase-3 QC.
PROMPT_CHAR_FLOOR = 1500      # HARD floor (AF-P1): any rich prompt under this is NOT run/rendered/updated — FAIL LOUD
PROMPT_CHAR_CEILING = 18000   # UNIVERSAL hard maximum (AF-P2; 2,000 under the 20,000 API ceiling)

# ---------------------------------------------------------------------------
# RESEARCH-CITATION GATE (AF-RESEARCH-UNCITED) — the minimum cited-URL floor
# ---------------------------------------------------------------------------
# A research brief that asserts research_complete:true but carries fewer than
# MIN_CITED_SOURCES real http(s) URLs is not a research pack — it is a
# self-reported completion that skipped the actual work.  This constant is the
# authoritative threshold.  It is intentionally named (not inlined) so sync_check
# can verify it exists and the PIPELINE-MANIFEST.json py_symbol can point at it.
#
# Rationale for 8:
#   The Deep Research SOP mandates categories A, B, C, D (D1+D2+D3), G, H, I, K, L
#   for a full brief — that is at minimum 10 categories, each requiring at least one
#   source URL.  8 is a conservative floor that catches the "zero research" case
#   (0-2 URLs, or a brief built entirely from intake with no external sources) while
#   not over-penalising a condensed micro-deck brief (which the SOP allows to be
#   smaller but still requires real external sources in C and D).
MIN_CITED_SOURCES = 8   # HARD floor (AF-RESEARCH-UNCITED): fewer real URLs = FAIL LOUD

# C3: counting raw http(s) URL strings is gameable — the same source cited 8 times,
# or 8 localhost/example.com/RFC-1918/bare-IP "URLs", all pass a naive count. The
# authoritative measure is DISTINCT REAL PUBLIC DOMAINS. MIN_DISTINCT_DOMAINS is the
# configurable floor on that count (kept separate from, and additive to,
# MIN_CITED_SOURCES so both constants stay referenced by sync_check / the manifest).
# 6 is the conservative floor: a real Deep-Research brief draws on many more, but a
# self-reported "research_complete" with fewer than 6 distinct public sources is not
# a research pack. Hosts that are NOT real public sources are excluded entirely:
#   * localhost / loopback (127.0.0.0/8, ::1)
#   * RFC-1918 / private + link-local IP ranges
#   * bare IP literals (a citation should name a source, not an IP)
#   * .local / .localhost / .internal / .example / .invalid / .test reserved TLDs
#   * example.* placeholder domains (example.com / example.org / example-source-*)
MIN_DISTINCT_DOMAINS = 6   # HARD floor on DISTINCT REAL PUBLIC domains (AF-RESEARCH-UNCITED)

# Reserved / non-routable TLD suffixes that are never a real public source.
_NON_PUBLIC_TLD_SUFFIXES = (
    ".local", ".localhost", ".internal", ".example", ".invalid", ".test",
)


def _registered_domain(netloc: str) -> Optional[str]:
    """Reduce a URL netloc to a real PUBLIC host, or None when the host is not a
    real public source. Strips userinfo + port, lowercases, then REJECTS (returns
    None) for: empty hosts, localhost/loopback, bare IP literals (any private OR
    public IP — a citation must name a source, not an address), RFC-1918 / link-local
    ranges, reserved non-public TLDs, and example.* placeholder domains. The returned
    value is the host used for de-duplication (distinct registered domains)."""
    host = (netloc or "").strip().lower()
    # Drop any userinfo (user:pass@) and port (:443).
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    # Strip a trailing :port (but not the colons inside an IPv6 literal in brackets).
    if host.startswith("["):
        # IPv6 literal like [::1]:443 -> ::1
        host = host[1:].split("]", 1)[0]
    elif ":" in host:
        host = host.rsplit(":", 1)[0]
    host = host.strip(".")
    if not host:
        return None
    # localhost variants.
    if host == "localhost" or host.endswith(".localhost"):
        return None
    # Reserved / non-public TLDs.
    for suffix in _NON_PUBLIC_TLD_SUFFIXES:
        if host.endswith(suffix):
            return None
    # example.* placeholder domains (example.com, example.org, example-source-*.org…).
    if host == "example" or host.startswith("example.") or host.startswith("example-"):
        return None
    # Bare IP literal? Reject (both private and public — cite a named source).
    try:
        ip = ipaddress.ip_address(host)
        # Any bare IP is not a named public source for our purposes.
        return None
    except ValueError:
        pass  # not an IP literal — it's a hostname, good.
    # A real public hostname must have at least one dot (a TLD).
    if "." not in host:
        return None
    return host


def _distinct_public_domains(text: str) -> set:
    """Extract every http(s) URL from text and return the set of DISTINCT REAL
    PUBLIC registered domains (junk/localhost/loopback/RFC-1918/.local/example.*/
    bare-IP hosts excluded). De-duplication is by host, so the same source cited N
    times counts once."""
    url_re = re.compile(r'https?://[^\s\)\]\>,\'"\\]+', re.IGNORECASE)
    domains = set()
    for raw in url_re.findall(text):
        try:
            netloc = urlparse(raw.rstrip(".")).netloc
        except ValueError:
            continue
        dom = _registered_domain(netloc)
        if dom:
            domains.add(dom)
    return domains

# Factual/statistical claim markers — tokens that signal a claim requiring a citation.
# When any of these appear in the slide copy and no corresponding cited URL exists in
# the research pack, the gate fires.  Documented heuristic: it catches the most common
# patterns (percentage figures, dollar figures, key research-signal words) without
# false-positives on purely narrative copy.
_CLAIM_MARKERS_RE_SRC = (
    r'\d+\s*%',                        # "45%", "20 %"
    r'\$\s*\d+',                       # "$5,000", "$ 3 million"
    r'\b(?:research|study|studies\s+show|statistics|data\s+shows)\b',
)

# ---------------------------------------------------------------------------
# FACIAL INTELLIGENCE / REPRESENTATION GUARD (the 60/30/10 landmine, fail-loud)
# ---------------------------------------------------------------------------
# Doctrine: SOP-CAST-01 ("No inverted default. There is no system default
# demographic.") and qc-specialist-presentations.md AF-R3 ("No racial or gender
# default is ever inferred."). Representation in any people-prompt MUST come from
# the slide spec (the client's captured audience), NEVER from a baked-in default
# percentage split such as the "60/30/10" ratio. This builder is deterministic
# and renders the scene VERBATIM from slides.json, so it must NEVER carry a
# hardcoded demographic default of its own, and it must REJECT a slide whose spec
# tries to smuggle one in. These patterns (case-insensitive substrings) are the
# forbidden demographic-default landmines; any of them in a slide's scene/copy/
# layout/logo text is an immediate fail-loud (the prompt-side representation gate).
FORBIDDEN_DEMOGRAPHIC_DEFAULTS = [
    "60/30/10",
    "60-30-10",
    "60/30/10 ratio",
    "default demographic",
    "default ethnicity",
    "default race",
    "default skin tone",
    "default skin-tone",
    "standard demographic mix",
    "standard representation mix",
    "assume the audience is",
    "assumed demographic",
    "inferred demographic",
    "system default demographic",
]

# Client's own env stores (HOME-relative — works on any client box).
SECRETS_CANDIDATES = [
    os.path.expanduser("~/.openclaw/workspace/.env"),
    os.path.expanduser("~/clawd/secrets/.env"),
    os.path.expanduser("~/.openclaw/secrets/.env"),
]

# ---------------------------------------------------------------------------
# OUTPUT DESTINATION — default ~/Downloads (Requirement 4)
# ---------------------------------------------------------------------------
# The final bundle dir defaults to ~/Downloads/<client-slug>-<deck-slug>/.
# --out overrides this. Files NEVER default to a scratch/run dir; they must
# land in ~/Downloads so the client receives them from a predictable location.
# The slug is derived from the deck slug (out.pptx stem) at runtime if present.
BUNDLE_DIR_DEFAULT = os.path.expanduser("~/Downloads")

# ---------------------------------------------------------------------------
# DELIVERABLES_REQUIRED manifest (Requirement 1)
# ---------------------------------------------------------------------------
# The nine mandatory output artifacts, their canonical relative paths inside the
# bundle dir, their per-artifact minimum-size gates, and a human description.
# Any artifact below its min_bytes threshold (or absent) triggers
# AF-BUNDLE-COMPLETE (exit 5). Rationale for each threshold:
#
#   deck_pptx  > 1 MB  : a real multi-slide rendered deck with 2K images is
#                         always several MB; < 1 MB implies the pptx is empty
#                         or contains placeholder content (zero-image shell < 100KB).
#
#   deck_pdf   > 50 KB : a minimal 1-slide PDF export is ~20-30KB; 50KB ensures
#                         at least two slides' worth of rendered content.
#
#   guide_pdf  > 50 KB : a minimal guide covers all slides with talking points and
#                         timing; < 50KB implies only a stub header.
#
#   speech_md  > 2 KB  : a word-for-word script for any real webinar talk will be
#                         thousands of words; 2KB floors an obvious empty or stub.
#
#   speech_pdf > 20 KB : a PDF export of a real speech; < 20KB implies a stub.
#
#   audio_mp3  > 500KB : a real Fish Audio S2 rendition of a 30-min script is
#                         typically 50-150MB; 500KB floors the obvious failure case
#                         (silence stub or failed render < 100KB per SOP-PITCH-05).
#
#   infographic_png > 100KB : a real 2K-resolution infographic checklist PNG is
#                              always several hundred KB; < 100KB implies a blank
#                              placeholder image or a tiny thumbnail.
#
DELIVERABLES_REQUIRED = [
    {
        "key": "deck_pptx",
        "filename": "{deck_slug}-FINAL.pptx",
        "label": "assembled deck PPTX",
        "min_bytes": 1_048_576,          # 1 MB — multi-slide 2K-image deck floor
        "note": ">1MB floor; a sub-1MB pptx implies empty/placeholder content",
    },
    {
        "key": "deck_pdf",
        "filename": "{deck_slug}-FINAL.pdf",
        "label": "deck PDF export",
        "min_bytes": 51_200,             # 50 KB — PDF export of at least 2 slides
        "note": ">50KB; produced by PPTX Assembly Specialist (LibreOffice/Pandoc export)",
    },
    {
        "key": "guide_pdf",
        "filename": "PRESENTER-GUIDE.pdf",
        "label": "presenter guide PDF",
        "min_bytes": 51_200,             # 50 KB — guide covers all slides with talking points
        "note": ">50KB; produced by Presenters Guide Specialist. REQUIRED UPSTREAM STEP.",
    },
    {
        "key": "speech_md",
        "filename": "PRESENTERS-SPEECH.md",
        "label": "presenter speech markdown source (pure)",
        "min_bytes": 2_048,              # 2 KB — word-for-word script stub floor
        "note": ">2KB; produced by Presenters Speech Writer (pure script). REQUIRED UPSTREAM STEP.",
    },
    {
        "key": "speech_pdf",
        "filename": "PRESENTERS-SPEECH.pdf",
        "label": "presenter speech teleprompter PDF",
        "min_bytes": 20_480,             # 20 KB — PDF of a real multi-page script
        "note": ">20KB; produced by Presenters Speech Writer (teleprompter PDF render). REQUIRED UPSTREAM STEP.",
    },
    {
        "key": "speech_fish_md",
        "filename": "PRESENTERS-SPEECH-FISH-TAGGED.md",
        "label": "presenter speech (Fish-Audio expression-tagged)",
        "min_bytes": 2_048,              # 2 KB — fish-tagged variant of the script floor
        "note": ">2KB; produced by Presenters Speech Writer / Fish Audio Expression "
                "Specialist (the (break)/(laugh)/emphasis-tagged script that feeds the "
                "audio render). REQUIRED UPSTREAM STEP.",
    },
    {
        "key": "audio_mp3",
        "filename": "PRESENTER-AUDIO.mp3",
        "label": "presenter audio MP3",
        "min_bytes": 512_000,            # 500 KB — real Fish Audio S2 rendition floor
        "note": ">500KB; produced by Audio Demonstration Specialist. REQUIRED UPSTREAM STEP.",
    },
    {
        "key": "infographic_png",
        "filename": "infographic.png",
        "label": "infographic checklist PNG",
        "min_bytes": 102_400,            # 100 KB — real 2K-resolution infographic floor
        "note": ">100KB; produced by infographic-checklist role. REQUIRED UPSTREAM STEP.",
    },
    {
        "key": "teleprompter_html",
        "filename": "presenter-teleprompter.html",
        "label": "presenter teleprompter web app",
        "min_bytes": 10_240,             # 10 KB — a real self-contained scrolling
                                          # teleprompter app (HTML + inline CSS/JS);
                                          # < 10KB implies an empty/stub page.
        "note": ">10KB; the standalone scrolling teleprompter app. Produced by the "
                "build_teleprompter.py generator (owned by the speech/teleprompter "
                "role). REQUIRED UPSTREAM STEP.",
    },
]


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def load_api_key() -> str:
    key = os.environ.get("KIE_API_KEY", "").strip()
    if key:
        return key.strip("'\"")
    for path in SECRETS_CANDIDATES:
        p = Path(path)
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line.startswith("KIE_API_KEY="):
                value = line[len("KIE_API_KEY="):].strip().strip("'\"")
                if value:
                    return value
    print("FATAL: KIE_API_KEY not found in env or any of:", file=sys.stderr)
    for path in SECRETS_CANDIDATES:
        print("   ", path, file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Rich per-slide prompt loading — VERBATIM, NO AI, NO THIN FALLBACK
# ---------------------------------------------------------------------------
# build_deck.py renders the Slide Image Creator's hand-authored RICH per-slide
# prompt VERBATIM. It NEVER composes its own thin scene+copy prompt. The rich
# prompt file for slide N lives in the run's working/prompts/ dir under one of
# these names (the CLIENT-WEBINAR-DECK-SOP convention first, then the
# slide-image-creator-sops.md convention):
PROMPT_FILE_PATTERNS = (
    "working/prompts/slide-{nn:02d}.txt",
    "working/prompts/slide-{nn:02d}-prompt.txt",
)


def resolve_prompt_path(run_dir: Path, ordinal: int) -> Optional[Path]:
    """Return the rich-prompt file Path for this slide ordinal, or None if no
    candidate file exists. Tries both the slide-NN.txt and slide-NN-prompt.txt
    naming conventions under working/prompts/."""
    for pat in PROMPT_FILE_PATTERNS:
        p = run_dir / pat.format(nn=ordinal)
        if p.exists() and p.is_file():
            return p
    return None


def assert_no_forbidden_demographic_default(slide: dict, prompt_text: str = "") -> None:
    """
    FACIAL-INTELLIGENCE / REPRESENTATION GATE (fail-loud).

    Representation must come from the slide spec / casting ledger (the client's
    captured audience), never from a baked-in default split. Per SOP-CAST-01
    ("there is no system default demographic") and AF-R3 ("no racial or gender
    default is ever inferred"), this builder REFUSES any slide whose author-supplied
    spec OR whose rich prompt text smuggles a forbidden demographic-default landmine
    (e.g. the "60/30/10" ratio). Raises ValueError (caller fails the slide loud) on
    a hit. prompt_text is the verbatim rich prompt being rendered — scanned too so a
    landmine in the prompt file (not just the slides.json spec) is also caught.
    """
    # Gather every author-supplied text field on this slide into one haystack,
    # plus the rich prompt text that will actually be sent to KIE.
    chunks = [str(slide.get("scene", "")), str(slide.get("layout", "")),
              str(slide.get("logo", "")), str(prompt_text)]
    copy_val = slide.get("copy", [])
    if isinstance(copy_val, list):
        chunks.extend(str(c) for c in copy_val)
    else:
        chunks.append(str(copy_val))
    haystack = " ".join(chunks).lower()

    for landmine in FORBIDDEN_DEMOGRAPHIC_DEFAULTS:
        if landmine.lower() in haystack:
            raise ValueError(
                f"slide {slide.get('slide')}: forbidden hardcoded demographic "
                f"default detected ('{landmine}'). Representation must come from "
                f"the client's captured audience / casting ledger, never a baked-in "
                f"default split (SOP-CAST-01 / AF-R3). Refusing to render."
            )


def load_rich_prompt(slide: dict, run_dir: Path) -> str:
    """
    Load the Slide Image Creator's RICH per-slide prompt VERBATIM and gate it.

    This is the ONLY prompt path. build_deck.py renders the hand-authored rich
    prompt (working/prompts/slide-NN.txt or slide-NN-prompt.txt) EXACTLY as written
    — it does NOT compose its own thin scene+copy prompt and NEVER silently falls
    back to one. The rich prompt already carries the full 15-element spec
    (typography per-line weight + pt size, placement, usage, the logo(s), the scene,
    the verbatim copy, the negative block — everything on the slide), and KIE
    (gpt-image-2) renders the WHOLE slide in ONE generation.

    FAIL LOUD (ValueError; the caller fails the slide and the run is blocked) when:
      * no rich prompt file exists for this slide                       → AF-P1
      * the rich prompt is < PROMPT_CHAR_FLOOR (1,500) chars            → AF-P1
        (not run, not rendered, not updated)
      * the rich prompt is > PROMPT_CHAR_CEILING (18,000) chars         → AF-P2
      * a forbidden demographic-default landmine is present             → AF-R3
      * the dead endpoint fragment is present
    """
    ordinal = int(slide["slide"])
    prompt_path = resolve_prompt_path(run_dir, ordinal)
    if prompt_path is None:
        tried = " or ".join(p.format(nn=ordinal) for p in PROMPT_FILE_PATTERNS)
        raise ValueError(
            f"slide {ordinal}: NO rich prompt file found (looked for {tried} under "
            f"{run_dir}). build_deck.py renders the Slide Image Creator's rich prompt "
            f"VERBATIM and NEVER composes a thin fallback. Refusing to render "
            f"(rich-prompt-required, AF-P1)."
        )

    prompt = prompt_path.read_text(errors="replace")

    # FACIAL-INTELLIGENCE / REPRESENTATION gate over the slide spec AND the verbatim
    # rich prompt (so a landmine in the prompt file is also caught).
    assert_no_forbidden_demographic_default(slide, prompt_text=prompt)

    # Self-guard: never let the dead endpoint string ride inside a prompt payload.
    if DEAD_ENDPOINT_FRAGMENT in prompt:
        raise ValueError(
            f"slide {ordinal}: rich prompt {prompt_path} contains the dead endpoint "
            f"fragment '{DEAD_ENDPOINT_FRAGMENT}'. Refusing."
        )

    # PROMPT CHAR-COUNT GATE (fail-loud). The floor is HARD (1,500): a prompt under
    # it is a thin stub / truncated file, NOT a real slide prompt — never run it.
    # H1: measure the STRIPPED length so a file padded with whitespace (or one that is
    # whitespace-only) can never satisfy the floor. len(prompt) over raw bytes would
    # let "   \n   ... 1500 spaces ..." pass as a "1,500-char prompt".
    if not prompt.strip():
        raise ValueError(
            f"slide {ordinal}: rich prompt {prompt_path} is empty / whitespace-only. "
            f"A blank prompt carries none of the mandatory per-slide spec. It is NOT "
            f"run, NOT rendered, NOT updated. Re-author the rich prompt. Refusing "
            f"(prompt char-count gate, AF-P1 floor)."
        )
    length = len(prompt.strip())
    if length < PROMPT_CHAR_FLOOR:
        raise ValueError(
            f"slide {ordinal}: rich prompt {prompt_path} is {length} chars, UNDER the "
            f"HARD floor of {PROMPT_CHAR_FLOOR}. A prompt this short cannot carry the "
            f"mandatory per-slide spec (typography size/placement/usage, logo, scene, "
            f"verbatim copy, negative block). It is NOT run, NOT rendered, and NOT "
            f"updated. Re-author the rich prompt to >= {PROMPT_CHAR_FLOOR} chars. "
            f"Refusing (prompt char-count gate, AF-P1 floor)."
        )
    if length > PROMPT_CHAR_CEILING:
        raise ValueError(
            f"slide {ordinal}: rich prompt {prompt_path} is {length} chars, over the "
            f"hard ceiling of {PROMPT_CHAR_CEILING} (2,000 under the 20,000 GPT-Image 2 API "
            f"ceiling, MODEL-SPECS). The prompt is too long; tighten redundant phrasing "
            f"(never delete the negative block or any spelling-lock). Refusing "
            f"(prompt char-count gate, AF-P2 ceiling)."
        )
    return prompt


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class RateLimited(Exception):
    pass


# C1 (SSRF / local-file read guard): the ONLY URL schemes this pipeline is ever
# allowed to open. urllib.request.urlopen will happily honour file://, ftp://,
# data:, etc. — so a KIE result URL, a --logo URL, or any API URL that resolves to
# anything other than http(s) is an SSRF / arbitrary-local-file-read landmine
# (e.g. file:///etc/passwd, file:///Users/.../secrets/.env). Every URL we open
# MUST pass this allowlist FIRST or we refuse, loud.
ALLOWED_URL_SCHEMES = ("http", "https")


def assert_url_scheme_allowed(url: str, what: str = "URL") -> None:
    """Refuse (ValueError) unless the URL's scheme is http or https. This is the
    SSRF / local-file-read guard (C1): urlopen honours file://, ftp://, data:, etc.,
    so before opening ANY fetched URL we enforce a strict http(s) allowlist. Applied
    to _http_json (the KIE API calls), download_unauthenticated (the KIE result URL),
    and the --logo URL path."""
    scheme = (urlparse(str(url)).scheme or "").lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        raise ValueError(
            f"REFUSED: {what} {url!r} has scheme {scheme!r}, which is not in the "
            f"allowlist {ALLOWED_URL_SCHEMES}. Only http(s) URLs may be opened "
            f"(file://, ftp://, data:, etc. are blocked — SSRF / local-file-read guard)."
        )


def _http_json(method: str, url: str, api_key: str, body: Optional[dict] = None) -> dict:
    assert_url_scheme_allowed(url, what="API URL")
    if DEAD_ENDPOINT_FRAGMENT in url:
        raise RuntimeError(
            f"REFUSED: attempted to call the dead endpoint {DEAD_ENDPOINT_FRAGMENT}. "
            "This pipeline only uses /api/v1/jobs/createTask and /api/v1/jobs/recordInfo."
        )
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimited(f"HTTP 429 from {url}")
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}\nResponse: {body_text}") from exc
    except urllib.error.URLError as exc:
        # Network unreachable — fail loud (no substitution).
        raise RuntimeError(f"NETWORK ERROR reaching {url}: {exc}. KIE is unreachable.") from exc


def submit_task(prompt: str, api_key: str, logo_url: Optional[str] = None) -> str:
    # OFFICIAL-LOGO mode = IMAGE-TO-IMAGE: pass the real logo URL as input_urls so
    # KIE (gpt-image-2-image-to-image) composites the ACTUAL logo into the slide
    # (the verified technique). No logo_url -> plain text-to-image.
    if logo_url:
        payload = {
            "model": MODEL_I2I,
            "input": {
                "prompt": prompt,
                "input_urls": [logo_url],
                "aspect_ratio": ASPECT_RATIO,
                "resolution": RESOLUTION,
            },
        }
    else:
        payload = {
            "model": MODEL_T2I,
            "input": {
                "prompt": prompt,
                "aspect_ratio": ASPECT_RATIO,
                "resolution": RESOLUTION,
            },
        }
    resp = _http_json("POST", CREATE_URL, api_key, body=payload)
    if resp.get("code") != 200:
        raise RuntimeError(f"createTask non-200 code. Full response: {json.dumps(resp)}")
    task_id = (resp.get("data") or {}).get("taskId")
    if not task_id:
        raise RuntimeError(f"createTask 200 but no taskId. Full response: {json.dumps(resp)}")
    return task_id


def poll_task(task_id: str, api_key: str) -> str:
    """Poll recordInfo every ~8s up to ~7 min. Returns resultUrls[0] on success.

    A genuinely failed/garbled render still fails loud: any terminal state
    ('fail'/'failed'/'error'/'cancelled') short-circuits immediately. The extra
    patience is ONLY for slides that keep reporting a healthy non-terminal state
    ('generating'/'waiting'/'queuing'/'processing'/'running') — those are merely
    slow, so if we reach the ceiling while the slide is still actively making
    progress we grant a bounded grace window rather than killing a healthy render.
    """
    url = f"{POLL_URL}?taskId={task_id}"

    # States KIE reports while a slide is healthily in-flight (not yet done, not failed).
    HEALTHY_INFLIGHT = ("generating", "waiting", "queuing", "queued", "processing", "running", "pending")

    # Grace: if the slide is STILL actively generating when the normal ceiling is hit,
    # allow up to this many extra passes (~25% more time) before declaring a timeout.
    # This only ever fires for slides that never reached a terminal-failure state.
    GRACE_PASSES = POLL_MAX_PASSES // 4  # ~13 extra passes (~104s) for slow renders

    deadline = time.time() + POLL_MAX_SECONDS
    passes = 0
    grace_used = 0
    last_state = ""
    # +2 normal slack passes, plus the grace passes so a healthy-but-slow render is
    # not cut short by the pass cap before its grace window is exhausted.
    while passes < POLL_MAX_PASSES + 2 + GRACE_PASSES:
        # Past the wall-clock deadline: only keep going if the slide is still a
        # healthy in-flight render AND we have grace passes left. Otherwise stop.
        if time.time() >= deadline:
            if last_state in HEALTHY_INFLIGHT and grace_used < GRACE_PASSES:
                grace_used += 1
                print(
                    f"    [poll grace {grace_used}/{GRACE_PASSES}] taskId={task_id} "
                    f"still {last_state!r} past {POLL_MAX_SECONDS}s; extending", flush=True
                )
            else:
                break
        passes += 1
        try:
            resp = _http_json("GET", url, api_key)
        except RateLimited:
            print(f"    [poll] 429 — sleeping {RATE_LIMIT_SLEEP_S}s", flush=True)
            time.sleep(RATE_LIMIT_SLEEP_S)
            continue
        data = resp.get("data") or {}
        state = str(data.get("state", "")).lower()
        last_state = state

        if state == "success":
            result_json_str = data.get("resultJson")
            if not result_json_str:
                raise RuntimeError(f"taskId {task_id}: success but no resultJson: {json.dumps(resp)}")
            result_obj = json.loads(result_json_str)
            urls = result_obj.get("resultUrls", [])
            if not urls:
                raise RuntimeError(f"taskId {task_id}: empty resultUrls: {json.dumps(result_obj)}")
            return urls[0]

        if state in ("fail", "failed", "error", "cancelled"):
            raise RuntimeError(
                f"taskId {task_id}: terminal state '{state}' "
                f"failCode={data.get('failCode')} failMsg={data.get('failMsg')}"
            )

        print(f"    [poll {passes}] taskId={task_id} state={state!r}; sleep {POLL_INTERVAL_S}s", flush=True)
        time.sleep(POLL_INTERVAL_S)

    raise RuntimeError(
        f"taskId {task_id}: not complete within {POLL_MAX_SECONDS}s "
        f"(+{grace_used * POLL_INTERVAL_S}s grace; last state {last_state!r})."
    )


def download_unauthenticated(url: str, dest: Path) -> None:
    """UNAUTHENTICATED GET of the CDN result URL (Bearer token causes 403)."""
    # C1 (SSRF / local-file-read guard): the result URL comes back from KIE's API.
    # Refuse anything that is not http(s) before opening it (a file:// result URL
    # would otherwise read an arbitrary local file into the slide PNG).
    assert_url_scheme_allowed(url, what="KIE result URL")
    req = urllib.request.Request(url, headers={"User-Agent": "build_deck/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def verify_png(path: Path) -> None:
    """Verify the downloaded file is a real, non-empty PNG."""
    if not path.exists():
        raise RuntimeError(f"{path}: file was not written.")
    size = path.stat().st_size
    if size == 0:
        raise RuntimeError(f"{path}: file is zero bytes.")
    with open(path, "rb") as f:
        magic = f.read(8)
    if magic[:4] != b"\x89PNG":
        raise RuntimeError(f"{path}: not a PNG (magic={magic[:8].hex()}, size={size}).")


# ---------------------------------------------------------------------------
# Per-slide render with retry
# ---------------------------------------------------------------------------

def render_slide(slide: dict, api_key: str, renders_dir: Path, run_dir: Path,
                 has_official_logo: bool = False, logo_url: Optional[str] = None) -> dict:
    """
    Render a single slide. Returns {"slide", "file", "taskId"} on success.
    Raises RuntimeError if all SLIDE_MAX_ATTEMPTS fail.

    The prompt is the Slide Image Creator's RICH per-slide prompt, loaded VERBATIM
    from working/prompts/ (no thin fallback). has_official_logo is accepted for API
    stability but does NOT mutate the prompt — the rich prompt already carries the
    full logo instruction; logo_url is what makes KIE composite the real logo via
    image-to-image (input_urls).
    """
    ordinal = int(slide["slide"])
    name = f"slide-{ordinal:02d}"
    out_path = renders_dir / f"{name}.png"
    prompt = load_rich_prompt(slide, run_dir)

    last_err = None
    for attempt in range(1, SLIDE_MAX_ATTEMPTS + 1):
        print(f"  [{name}] attempt {attempt}/{SLIDE_MAX_ATTEMPTS}", flush=True)
        try:
            # submit (429-aware)
            while True:
                try:
                    task_id = submit_task(prompt, api_key, logo_url=logo_url)
                    break
                except RateLimited:
                    print(f"    [submit] 429 — sleeping {RATE_LIMIT_SLEEP_S}s", flush=True)
                    time.sleep(RATE_LIMIT_SLEEP_S)
            print(f"    submitted -> taskId={task_id}", flush=True)
            result_url = poll_task(task_id, api_key)
            print(f"    success resultUrls[0]={result_url}", flush=True)
            download_unauthenticated(result_url, out_path)
            verify_png(out_path)
            size = out_path.stat().st_size
            print(f"    downloaded+verified -> {out_path} ({size:,} bytes)", flush=True)
            return {"slide": ordinal, "file": str(out_path), "taskId": task_id}
        except Exception as exc:  # noqa: BLE001 — deliberately catch to retry
            last_err = exc
            print(f"    FAIL attempt {attempt}: {exc}", file=sys.stderr, flush=True)
            if attempt < SLIDE_MAX_ATTEMPTS:
                time.sleep(3)

    raise RuntimeError(f"{name}: failed after {SLIDE_MAX_ATTEMPTS} attempts. Last error: {last_err}")


# ---------------------------------------------------------------------------
# pptx assembly — full-bleed picture per slide, NO text boxes
# ---------------------------------------------------------------------------

def _logo_dimensions_in(logo_path: Path):
    """Return (width_in, height_in) for the composited logo: width fixed at
    LOGO_WIDTH_FRACTION of the slide width, height derived from the logo's native
    pixel aspect ratio so the EXACT client file is never distorted. Falls back to a
    square box if the image dimensions can't be read."""
    width_in = SLIDE_WIDTH_IN * LOGO_WIDTH_FRACTION
    try:
        from PIL import Image  # optional; only used to preserve aspect ratio
        with Image.open(str(logo_path)) as im:
            px_w, px_h = im.size
        if px_w > 0:
            height_in = width_in * (px_h / px_w)
        else:
            height_in = width_in
    except Exception:  # noqa: BLE001 — PIL absent or unreadable: assume square
        height_in = width_in
    return width_in, height_in


# ---------------------------------------------------------------------------
# PER-SLIDE SPEAKER NOTES — parse the presenter speech into per-slide chunks
# ---------------------------------------------------------------------------
# The Presenters Speech Writer authors a word-for-word script segmented per slide.
# Each slide's block is introduced by a SLIDE marker in one of two forms:
#       ## Slide 7          (a markdown heading, 1-3 '#'s, "Slide" any case)
#       SLIDE 7             (an inline marker with no heading hashes)
# parse_speech_chunks splits the speech on those markers and returns
#   {slide_no: spoken_text}
# where spoken_text is the block AFTER the marker/title line, up to the next marker
# (the marker/title line itself is stripped — it is a structural cue, not spoken).
#
# This is best-effort and NON-FATAL by contract: a speech with no recognisable
# markers yields {} and the caller injects no notes. Mismatches are handled by the
# caller (extra chunks are skipped; deck slides with no chunk get empty notes).

# Matches both "## Slide 7" (markdown heading) and inline "SLIDE 7". The optional
# leading 1-3 '#'s + whitespace cover the heading form; the marker word is matched
# case-insensitively (re.I) and anchored to the start of a line (re.M).
SPEECH_SLIDE_MARKER_RE = re.compile(r"^(?:#{1,3}\s+)?SLIDE\s+(\d+)\b", re.IGNORECASE | re.MULTILINE)


def parse_speech_chunks(speech_text: str) -> dict:
    """Parse a presenter-speech string into {slide_no: spoken_text}.

    Recognises BOTH marker forms (see SPEECH_SLIDE_MARKER_RE):
        '## Slide N' / '# Slide N' / '### Slide N'  (markdown heading)
        'SLIDE N'                                    (inline marker)
    For each marker, captures the text from the END of the marker line up to the
    start of the NEXT marker (or end of file), then strips surrounding whitespace.
    The marker/title line is NOT included in the spoken text.

    Returns {} when speech_text is empty/None or contains no recognisable markers
    (best-effort, never raises). If the same slide number appears more than once,
    the LAST occurrence wins (a later, fuller block supersedes an earlier stub)."""
    if not speech_text:
        return {}

    chunks: dict = {}
    matches = list(SPEECH_SLIDE_MARKER_RE.finditer(speech_text))
    if not matches:
        return {}

    for idx, m in enumerate(matches):
        try:
            slide_no = int(m.group(1))
        except (TypeError, ValueError):
            continue
        # Spoken text starts at the END of the marker LINE (skip the rest of the
        # marker/title line, which may carry a slide title after the number).
        line_end = speech_text.find("\n", m.end())
        block_start = (line_end + 1) if line_end != -1 else len(speech_text)
        # Spoken text ends at the start of the NEXT marker, else end of file.
        block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(speech_text)
        spoken = speech_text[block_start:block_end].strip()
        # Last occurrence of a slide number wins (supersedes an earlier stub).
        chunks[slide_no] = spoken
    return chunks


def discover_speech_chunks(run_dir: Path, bundle_dir: Path) -> Optional[dict]:
    """Auto-discover the presenter speech and parse it into per-slide chunks for
    PPTX speaker-notes injection. NON-FATAL: this is a phase-4 render and the speech
    is a phase-9 artifact, so the speech is frequently absent. Returns the parsed
    {slide_no: spoken_text} dict when a speech file is found, or None when none is
    present (caller then injects no notes). NEVER raises and NEVER blocks the render.

    Search order (first hit wins): the working-dir locations the speech roles write
    to, then the delivered bundle copy. Filenames use the standardized possessive
    (PRESENTERS-SPEECH.md); the legacy speech.md scratch name is also accepted."""
    candidates = [
        run_dir / "working/presenter-speech/speech.md",
        run_dir / "working/delivery/PRESENTERS-SPEECH.md",
        run_dir / "working/presenter-speech/PRESENTERS-SPEECH.md",
        bundle_dir / "PRESENTERS-SPEECH.md",
    ]
    for path in candidates:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError as exc:
            print(f"=== SPEAKER NOTES: found {path} but could not read it ({exc}); "
                  f"rendering deck WITHOUT per-slide notes (non-fatal) ===", flush=True)
            return None
        chunks = parse_speech_chunks(text)
        if chunks:
            print(f"=== SPEAKER NOTES: parsed {len(chunks)} per-slide chunk(s) from "
                  f"{path} — injecting into the deck's notes pane ===", flush=True)
        else:
            print(f"=== SPEAKER NOTES: speech found at {path} but no 'Slide N' / "
                  f"'## Slide N' markers were recognised; rendering deck WITHOUT "
                  f"per-slide notes (non-fatal) ===", flush=True)
        return chunks
    print("=== SPEAKER NOTES: no presenter speech found yet (searched "
          "working/presenter-speech/, working/delivery/, and the bundle dir). This is "
          "a phase-4 render; the speech is a phase-9 artifact. Rendering the deck "
          "WITHOUT per-slide notes (non-fatal — never blocks the render). ===",
          flush=True)
    return None


def assemble_pptx(rendered: list, out_path: Path, logo_path: Optional[Path] = None,
                  speech_chunks: Optional[dict] = None) -> None:
    try:
        from pptx import Presentation
        from pptx.util import Inches
    except ImportError:
        print("FATAL: python-pptx is not installed (pip install python-pptx).", file=sys.stderr)
        sys.exit(2)

    prs = Presentation()
    # 16:9 at the dept-documented dimensions.
    prs.slide_width = Inches(SLIDE_WIDTH_IN)
    prs.slide_height = Inches(SLIDE_HEIGHT_IN)
    blank = prs.slide_layouts[6]  # blank layout — no placeholders

    # Pre-compute the official-logo geometry ONCE so every slide gets the EXACT
    # same file at the EXACT same size/position (consistent top-right corner).
    logo_geom = None
    if logo_path is not None:
        logo_w_in, logo_h_in = _logo_dimensions_in(logo_path)
        logo_left_in = SLIDE_WIDTH_IN - LOGO_MARGIN_IN - logo_w_in
        logo_top_in = LOGO_MARGIN_IN
        logo_geom = (logo_left_in, logo_top_in, logo_w_in, logo_h_in)

    for item in sorted(rendered, key=lambda r: r["slide"]):
        slide = prs.slides.add_slide(blank)
        # Full-bleed background first.
        slide.shapes.add_picture(
            item["file"], 0, 0, width=Inches(SLIDE_WIDTH_IN), height=Inches(SLIDE_HEIGHT_IN)
        )
        # Then the EXACT official logo on top, top-right. add_picture writes the PNG
        # bytes verbatim, so RGBA transparency is preserved over the background.
        if logo_geom is not None:
            left_in, top_in, w_in, h_in = logo_geom
            slide.shapes.add_picture(
                str(logo_path),
                Inches(left_in), Inches(top_in),
                width=Inches(w_in), height=Inches(h_in),
            )

        # PER-SLIDE SPEAKER NOTES: if a parsed speech chunk exists for this slide
        # ordinal, write the spoken text into the slide's notes pane. None/{} =>
        # no injection (phase-4 render before the speech is written). Touching
        # notes_slide lazily creates the notes part, so a deck slide with no chunk
        # is left with no notes part at all — never an empty injection.
        if speech_chunks:
            spoken = speech_chunks.get(item["slide"])
            if spoken:
                slide.notes_slide.notes_text_frame.text = spoken

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))


# ---------------------------------------------------------------------------
# PROCESS PREFLIGHT GATE — refuse to render without the upstream dept artifacts
# ---------------------------------------------------------------------------
#
# build_deck.py is ONLY the deterministic Phase-4 renderer + a stripped Phase-8
# assembler. The real department flow wraps it in research, copy, two human gates,
# and four QC gates (see the Presentations dept SOPs). A hand-fed slides.json that
# skips all of that produces a .pptx that is technically valid but is NOT a
# process-compliant deliverable. This preflight makes that bypass fail LOUD.
#
# Each entry: (relative-glob-under-run-dir, human label, producing phase/role,
#              completeness-check callable). The completeness check receives the
# resolved Path (or None when the file is absent) and returns "" when satisfied
# or a short reason string when the artifact exists but is not complete.

def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return {"__parse_error__": str(exc)}


# The three DEFINITIVE audience modes (additive to presentation_mode; SOP-CAST /
# Director intake). STANDARD = net-new from a brainstorm; PERSONAL = built from the
# client's own content for a NAMED recipient; GENERAL = built from the client's own
# content but DE-IDENTIFIED. Captured in intake.json as audience_mode (uppercase).
AUDIENCE_MODES = ("STANDARD", "PERSONAL", "GENERAL")


def _chk_intake(path: Optional[Path]) -> str:
    if path is None:
        return "file absent"
    obj = _read_json(path)
    if "__parse_error__" in obj:
        return f"not valid JSON ({obj['__parse_error__']})"
    if obj.get("interview_confirmed") is not True:
        return "interview_confirmed is not true"
    # Existing presentation_mode (one-person | general) — UNCHANGED, still required.
    mode = str(obj.get("presentation_mode", "")).strip().lower()
    if mode not in ("one-person", "general"):
        return f"presentation_mode must be 'one-person' or 'general' (got {obj.get('presentation_mode')!r})"
    # Additive: the definitive audience_mode (STANDARD | PERSONAL | GENERAL).
    audience_mode = str(obj.get("audience_mode", "")).strip().upper()
    if audience_mode not in AUDIENCE_MODES:
        return (f"audience_mode must be one of {AUDIENCE_MODES} (got "
                f"{obj.get('audience_mode')!r}). STANDARD=net-new from brainstorm; "
                f"PERSONAL=from client content, named recipient; GENERAL=from client "
                f"content, de-identified.")
    # PERSONAL is the only NAMED mode — it must carry a recipient_name.
    if audience_mode == "PERSONAL" and not str(obj.get("recipient_name", "")).strip():
        return "audience_mode is PERSONAL but recipient_name is empty (PERSONAL is the named mode)."
    # Additive: target_talk_minutes — the speaking-length target the deck is sized to
    # (slides/copy/speech sized to target x 130 wpm). Must be a positive number.
    raw = obj.get("target_talk_minutes")
    try:
        if raw is None or float(raw) <= 0:
            return (f"target_talk_minutes must be a positive number of minutes "
                    f"(got {raw!r}). The deck/copy/speech are sized to "
                    f"target_talk_minutes x 130 wpm.")
    except (TypeError, ValueError):
        return f"target_talk_minutes is not numeric (got {raw!r})."
    return ""


def _chk_research_brief(path: Optional[Path]) -> str:
    if path is None:
        return "no working/research/brief-*.md found"
    text = path.read_text(errors="replace")
    low = text.lower()
    if "research_complete:true" not in low.replace(" ", ""):
        # tolerate 'research_complete: true' spacing
        if "research_complete" not in low or "true" not in low.split("research_complete", 1)[1][:40].lower():
            return "research_complete:true not present"
    return ""


def _chk_copy_qc(path: Optional[Path]) -> str:
    if path is None:
        return "file absent"
    obj = _read_json(path)
    if "__parse_error__" in obj:
        return f"not valid JSON ({obj['__parse_error__']})"
    # M1: require gate == "Phase 1Q" AFFIRMATIVELY. The old check (`if gate and gate
    # != "Phase 1Q"`) let an EMPTY/missing gate short-circuit straight past — a QC
    # report with no gate field would silently pass. The gate must be exactly the
    # Phase 1Q gate, present and correct.
    gate = str(obj.get("gate", "")).strip()
    if gate != "Phase 1Q":
        return f"gate is {gate!r}, expected 'Phase 1Q' (must be present and exactly 'Phase 1Q')"
    avg = obj.get("average", obj.get("average_score"))
    try:
        if avg is None or float(avg) < 8.5:
            return f"average score {avg!r} is below the 8.5 pass threshold"
    except (TypeError, ValueError):
        return f"average score {avg!r} is not numeric"
    # any triggered autofail blocks
    triggered = obj.get("triggered_autofails") or obj.get("autofails_triggered") or []
    if triggered:
        return f"triggered autofails present: {triggered}"
    # M1: require pass IS True affirmatively. The old check only rejected pass:false,
    # so a report with pass absent / null / a non-True value slipped through. A QC
    # report must explicitly assert pass:true.
    if obj.get("pass") is not True:
        return f"report does not affirmatively mark pass:true (got pass={obj.get('pass')!r})"
    return ""


def _chk_arc(path: Optional[Path]) -> str:
    # Signature Presentation Architect — the converting-arc allocation must exist.
    if path is None:
        return "file absent — Signature Presentation Architect did not produce the converting arc (arc_allocation)"
    obj = _read_json(path)
    if "__parse_error__" in obj:
        return f"not valid JSON ({obj['__parse_error__']})"
    slots = obj if isinstance(obj, list) else (obj.get("slots") or obj.get("allocation") or obj.get("slides"))
    if not slots:
        return "no per-slide arc-section allocation present (Architect arc not built)"
    return ""


def _chk_slides_copy(path: Optional[Path]) -> str:
    # Slide Copywriter — authored copy per doctrine must exist (Copy-QC validates depth).
    if path is None:
        return "file absent — Slide Copywriter did not author slides_copy (copy doctrine skipped)"
    if len(path.read_text(errors="replace").strip()) < 500:
        return "slides_copy is near-empty (Slide Copywriter doctrine not applied)"
    return ""


def _chk_design_brief(path: Optional[Path]) -> str:
    # Typography Architect / design research — per-slide creative art-direction brief must exist.
    if path is None:
        return "file absent — no design/typography brief (Typography Architect did not art-direct the slides)"
    if len(path.read_text(errors="replace").strip()) < 200:
        return "design/typography brief is near-empty (creative art-direction skipped)"
    return ""


def _count_output_slides(run_dir: Path, slides_path: Optional[Path] = None) -> Optional[int]:
    """Count the slides the system is about to output. Returns None when no count
    can be read.

    H3: when slides_path is supplied it is the ACTUAL positional slides.json the
    renderer will render (main()'s positional[0]). Counting it FIRST means the
    coverage gate and the rich-prompt gate derive their slide count from the EXACT
    file that gets rendered — not a different canonical-path slides.json that might
    have a different slide count (which would let the coverage / rich-prompt gates be
    bypassed by feeding one file to the gate and rendering another). Only when no
    explicit path is given (or it can't be read) do we fall back to the canonical
    working/copy/slides.json spots, then arc_allocation.json."""
    def _count_from(p: Path) -> Optional[int]:
        if not p.exists():
            return None
        obj = _read_json(p)
        if isinstance(obj, list):
            return len(obj)
        if isinstance(obj, dict) and "__parse_error__" not in obj:
            slides = obj.get("slides")
            if isinstance(slides, list):
                return len(slides)
        return None

    # 0. The ACTUAL rendered file (positional slides.json), when threaded in.
    if slides_path is not None:
        n = _count_from(slides_path)
        if n is not None:
            return n

    # 1. slides.json — the renderer's direct input. Look in a few canonical spots.
    for rel in ("working/copy/slides.json", "slides.json", "working/slides.json"):
        p = run_dir / rel
        n = _count_from(p)
        if n is not None:
            return n
    # 2. arc_allocation.json — per-slide arc-section allocation.
    arc = run_dir / "working" / "copy" / "arc_allocation.json"
    if arc.exists():
        obj = _read_json(arc)
        if "__parse_error__" not in obj:
            slots = obj if isinstance(obj, list) else (
                obj.get("slots") or obj.get("allocation") or obj.get("slides"))
            if isinstance(slots, list):
                return len(slots)
    return None


def _chk_research_cited(path: Optional[Path]) -> str:
    """RESEARCH-CITATION GATE (AF-RESEARCH-UNCITED, fail-loud).

    The existing _chk_research_brief gate only checks that research_complete:true
    appears in the file header — a flag any model can self-assert without doing any
    research.  This gate is the source of truth: it IGNORES the self-asserted flag
    and instead counts real authoritative http(s) URLs in the research pack.

    The gate FAILS LOUD when:
      * The research pack exists but contains fewer than MIN_CITED_SOURCES (8)
        distinct http(s) URLs.  This proves the brief was built from intake alone,
        not from real web research.

    When the file is absent, this check returns "" (the existing _chk_research_brief
    gate already produces a clear "file absent" failure for that case; we do not
    double-report it here).  The check is strictly ADDITIVE — it never weakens the
    existing research_complete:true check.

    Heuristic documented (C3): we extract every http(s) URL, reduce each to its
    REGISTERED DOMAIN (urlparse(...).netloc), and de-duplicate by domain. Junk hosts
    are EXCLUDED outright — localhost/loopback, RFC-1918 / link-local IPs, bare IP
    literals, .local/.internal/.invalid/.test/.example reserved TLDs, and example.*
    placeholder domains. The gate then requires at least MIN_DISTINCT_DOMAINS (6)
    DISTINCT REAL PUBLIC domains. This defeats the three ways the old raw-URL count
    was gamed: (1) the same source cited many times, (2) localhost/RFC-1918/bare-IP
    "URLs", and (3) example.com placeholders. MIN_CITED_SOURCES stays the named,
    configurable floor referenced by sync_check / the manifest; the effective gate is
    the distinct-public-domain count.
    """
    if path is None:
        return ""  # file-absent handled by _chk_research_brief; don't double-report

    text = path.read_text(errors="replace")
    domains = _distinct_public_domains(text)
    n = len(domains)
    if n < MIN_DISTINCT_DOMAINS:
        return (
            f"AF-RESEARCH-UNCITED: research pack at {path.name} cites {n} distinct "
            f"real public domain(s), below the HARD floor of {MIN_DISTINCT_DOMAINS} "
            f"(MIN_CITED_SOURCES={MIN_CITED_SOURCES}). Junk hosts (localhost, "
            f"loopback, RFC-1918 / private IPs, bare IP literals, .local/.internal/"
            f".example reserved TLDs, and example.* placeholders) are NOT counted — "
            f"so a research_complete:true flag, the same source cited many times, or "
            f"a list of localhost/example.com URLs is not proof of real web research. "
            f"The research pack MUST cite at least {MIN_DISTINCT_DOMAINS} DISTINCT, "
            f"real, authoritative public sources (covering categories A/B/C/D/G/H/I/K/L "
            f"per the Deep Research SOP). Re-run Phase -0.5 (Deep Research Specialist) "
            f"and cite every distinct source you find."
        )
    return ""


def _chk_claims_without_citation(run_dir: Path) -> str:
    """CLAIMS-WITHOUT-CITATION gate (AF-RESEARCH-UNCITED, fail-loud).

    Scans the slide copy (working/copy/slides.json or working/copy/slides_copy.md)
    for factual/statistical claim markers (a percentage, a dollar figure, the words
    'research'/'study'/'studies show'/'statistics'/'data shows') and fails if such
    a marker appears but the research pack contains NO corresponding cited URL.

    Documented heuristic: this is a presence gate, not a semantic match.  If ANY
    claim marker is found in the copy AND the research pack has zero URLs, the deck
    is shipping unsupported claims.  If the research pack has >= MIN_CITED_SOURCES
    URLs (meaning _chk_research_cited already passed), this check passes — the
    researcher's responsibility is to ensure each claim is supported; the mechanical
    gate proves a research pack with citations exists.  This prevents the case where
    zero research was done but the brief self-reports research_complete:true.

    Both checks (this + _chk_research_cited) are wired into PREFLIGHT_REQUIRED so
    neither can be silently skipped.  When the research pack has no URLs at all AND
    the copy has claim markers, we return the failure; otherwise we pass.
    """
    import re as _re

    # Locate the slide copy (json or markdown).
    copy_text = ""
    for rel in ("working/copy/slides.json", "working/copy/slides_copy.md",
                "slides.json", "working/slides.json"):
        cp = run_dir / rel
        if cp.exists():
            copy_text = cp.read_text(errors="replace")
            break
    if not copy_text.strip():
        return ""  # no copy found — nothing to check

    # Check for factual/statistical claim markers in the copy.
    claim_re = _re.compile(
        "|".join(_CLAIM_MARKERS_RE_SRC), _re.IGNORECASE)
    has_claims = bool(claim_re.search(copy_text))
    if not has_claims:
        return ""  # no claim markers — gate not triggered

    # Check whether ANY cited URL exists in the research pack.
    brief_matches = sorted(run_dir.glob("working/research/brief-*.md"))
    if not brief_matches:
        # No research pack at all + claims in copy = fail loud.
        return (
            "AF-RESEARCH-UNCITED: slide copy contains factual/statistical claim "
            "markers (a percentage, a dollar figure, or 'research'/'study'/"
            "'studies show'/'statistics'/'data shows') but no research pack "
            "(working/research/brief-*.md) was found. Claims on slides MUST be "
            "backed by a cited research pack. Run Phase -0.5 (Deep Research "
            "Specialist) and cite every source before copy proceeds to render."
        )

    # H4: union the cited domains across ALL brief-*.md files, not just the
    # alphabetically-first one (a single deck routinely splits research across
    # several brief files; reading only brief_matches[0] would miss real citations
    # in the others and wrongly fail). C3: count DISTINCT REAL PUBLIC domains, not
    # raw URL strings, so localhost/example.com/RFC-1918/bare-IP/dup "URLs" do not
    # count as citations here either.
    all_domains = set()
    for bm in brief_matches:
        all_domains |= _distinct_public_domains(bm.read_text(errors="replace"))
    if not all_domains:
        names = ", ".join(b.name for b in brief_matches)
        return (
            f"AF-RESEARCH-UNCITED: slide copy contains factual/statistical claim "
            f"markers but the research pack ({names}) contains zero cited real public "
            f"http(s) sources (localhost / example.* / RFC-1918 / bare-IP hosts are "
            f"not counted). Every claim in slide copy that cites a percentage, dollar "
            f"figure, or research finding MUST have a corresponding citation in the "
            f"research pack. Re-run Phase -0.5 and add real cited sources before render."
        )
    return ""


def _chk_coverage(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """ANTI-COMPRESSION (AF-COVERAGE-1). Mode B (working from a client's existing
    deck) is ADD-only: the output deck must NEVER have fewer slides than the source
    deck. Reads mission_prd.json's top-level integer 'source_slide_count' (Mode A =
    absent/0, which always passes) and compares to the output slide count from
    slides.json (or arc_allocation.json). Returns "" on pass, or a fatal AF message
    string (run_preflight maps a returned reason to exit 3)."""
    # Resolve mission_prd.json (Mode A: absent -> source 0 -> always pass).
    source = 0
    for rel in ("working/copy/mission_prd.json", "mission_prd.json",
                "working/mission_prd.json"):
        p = run_dir / rel
        if p.exists():
            obj = _read_json(p)
            if isinstance(obj, dict) and "__parse_error__" not in obj:
                raw = obj.get("source_slide_count", 0)
                try:
                    source = int(raw)
                except (TypeError, ValueError):
                    source = 0
            break

    if source <= 0:
        return ""  # Mode A — no client source deck; coverage check does not apply.

    # H3: count the ACTUAL rendered slides.json (positional) when threaded in.
    final = _count_output_slides(run_dir, slides_path)
    if final is None:
        # We have a source count but cannot read the output count — cannot prove
        # coverage, so fail rather than silently pass a possibly-compressed deck.
        return (f"AF-COVERAGE-1: source deck had {source} slides but the output "
                f"slide count could not be read (no slides.json/arc_allocation.json). "
                f"The system must NEVER output fewer slides than the source "
                f"(Mode B is ADD-only).")

    if final < source:
        return (f"AF-COVERAGE-1: output deck has {final} slides; client source deck "
                f"had {source}. The system must NEVER output fewer slides than the "
                f"source (Mode B is ADD-only). Add {source - final} slides.")
    return ""


def _chk_rich_prompts(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """RICH-PROMPT-REQUIRED gate (AF-P1). EVERY slide the system is about to render
    MUST have a hand-authored RICH per-slide prompt in working/prompts/ that is
    >= PROMPT_CHAR_FLOOR (1,500) chars. A missing prompt file, or one under the
    floor, is an AF-P1 auto-fail: build_deck.py renders the rich prompt VERBATIM and
    NEVER composes a thin fallback, so a thin/absent prompt means the slide cannot be
    rendered at all. Returns "" on pass, or a fatal AF-P1 message (run_preflight maps
    a returned reason to exit 3). The 18,000 ceiling (AF-P2) is enforced per-slide at
    render time in load_rich_prompt (a too-long prompt still passes preflight; it is
    the floor + presence that are the un-bypassable pre-render gate here)."""
    # H3: count the ACTUAL rendered slides.json (positional) when threaded in, so the
    # rich-prompt gate verifies a prompt for every slide that will actually render.
    n = _count_output_slides(run_dir, slides_path)
    if n is None:
        return ("AF-P1: cannot determine the slide count (no slides.json / "
                "arc_allocation.json), so the per-slide rich prompts cannot be "
                "verified. Produce slides.json before render.")
    problems = []
    for ordinal in range(1, n + 1):
        p = resolve_prompt_path(run_dir, ordinal)
        if p is None:
            problems.append(f"slide {ordinal:02d}: NO rich prompt file in working/prompts/")
            continue
        # H1: measure the STRIPPED length so a whitespace-padded / whitespace-only
        # prompt file can never satisfy the floor.
        length = len(p.read_text(errors="replace").strip())
        if length < PROMPT_CHAR_FLOOR:
            problems.append(
                f"slide {ordinal:02d}: rich prompt {p.name} is {length} non-whitespace "
                f"chars, under the {PROMPT_CHAR_FLOOR}-char HARD floor")
    if problems:
        head = (f"AF-P1: rich-prompt-required gate FAILED for {len(problems)} of {n} "
                f"slides. build_deck.py renders the Slide Image Creator's rich prompt "
                f"VERBATIM (working/prompts/slide-NN.txt or slide-NN-prompt.txt) and "
                f"never composes a thin fallback; each must be >= {PROMPT_CHAR_FLOOR} "
                f"chars. Offenders:")
        return head + " | " + "; ".join(problems)
    return ""


# Speech-length gate floor: the presenter speech must carry at least
# target_talk_minutes x SPEECH_WPM_FLOOR words. 120 wpm is the LOW end of the
# verified 120-140 absorption band the Presenter Speech Writer cites (the deck is
# paced at 130 wpm; a script that lands below 120 wpm of content is too SHORT for
# the chosen duration). This is the floor only — the +/-10% pacing budget around
# 130 wpm stays with the Presenter Speech Writer / Presenter Coach.
SPEECH_WPM_FLOOR = 120


def _chk_speech_length(run_dir: Path) -> str:
    """SPEECH-LENGTH gate (AF-SPEECH-SHORT). Once the presenter speech exists, its
    word count must be >= target_talk_minutes x SPEECH_WPM_FLOOR (120 wpm). A speech
    shorter than that does not fill the duration the client asked for and FAILS short.

    This gate is CONDITIONAL by design: the speech is written downstream (Phase 9
    delivery), AFTER the deterministic render. So when no speech artifact exists yet,
    this returns "" (the render is allowed to proceed — the gate fires at delivery,
    not at render). When a speech file IS present, it is enforced. Either way the
    gate is wired into the lockstep so it can never be silently skipped once the
    speech is written. Returns "" on pass/not-applicable, or a fatal AF message."""
    # target_talk_minutes comes from intake.json (the field _chk_intake requires).
    target = None
    for rel in ("working/copy/intake.json", "intake.json", "working/intake.json"):
        p = run_dir / rel
        if p.exists():
            obj = _read_json(p)
            if isinstance(obj, dict) and "__parse_error__" not in obj:
                raw = obj.get("target_talk_minutes")
                try:
                    target = float(raw) if raw is not None else None
                except (TypeError, ValueError):
                    target = None
            break
    if not target or target <= 0:
        # No usable target (intake gate handles a missing target). Not applicable here.
        return ""

    # Locate the speech artifact. Absent => deferred to delivery (pass here).
    # Filenames standardized to the possessive (PRESENTERS-SPEECH.md); the legacy
    # singular (PRESENTER-SPEECH.md) and scratch speech.md names are still accepted
    # so the gate keeps finding a speech written by an older flow.
    speech = None
    for rel in ("working/presenter-speech/speech.md",
                "working/delivery/PRESENTERS-SPEECH.md",
                "working/presenter-speech/PRESENTERS-SPEECH.md",
                "working/delivery/PRESENTER-SPEECH.md",
                "working/presenter-speech/PRESENTER-SPEECH.md"):
        p = run_dir / rel
        if p.exists():
            speech = p
            break
    if speech is None:
        return ""  # speech not written yet (pre-delivery render) — gate defers.

    words = len(speech.read_text(errors="replace").split())
    floor = int(round(target * SPEECH_WPM_FLOOR))
    if words < floor:
        return (f"AF-SPEECH-SHORT: presenter speech {speech.name} has {words} words; "
                f"the floor for a {target:g}-minute talk is {floor} words "
                f"(target_talk_minutes x {SPEECH_WPM_FLOOR} wpm). The speech is too "
                f"SHORT to fill the requested duration. Lengthen it.")
    return ""


# The MANDATORY pre-render artifact set. The first three are the minimum the
# operator task names explicitly; the rest are the broader mandatory upstream set
# from the dept-pipeline analysis. All must exist + be complete before any render.
PREFLIGHT_REQUIRED = [
    ("working/copy/intake.json",
     "intake.json (interview_confirmed:true, presentation_mode one-person|general)",
     "Phase 0a — Director SOP 9.1 / Content-to-Presentation Architect SOP 9.1",
     _chk_intake),
    ("working/research/brief-*.md",
     "research brief (research_complete:true)",
     "Phase -0.5 — Deep Research Specialist SOP 9.1/9.4 (AF-RESEARCH-GATE)",
     _chk_research_brief),
    # 10th check — RESEARCH-CITATION GATE (AF-RESEARCH-UNCITED). The research pack
    # must contain >= MIN_CITED_SOURCES (8) distinct http(s) URLs, proving real web
    # research was done. The self-asserted research_complete:true flag is IGNORED
    # here — this gate is the source of truth for whether citations exist.
    # Uses rel glob (same as research brief) so the first matching brief file is
    # passed to the checker.
    ("working/research/brief-*.md",
     f"research pack cited URLs — >= {MIN_CITED_SOURCES} distinct http(s) URLs "
     f"required (self-asserted research_complete:true flag is not proof of research)",
     "Phase -0.5 — Deep Research Specialist SOP 9.1/9.4 (AF-RESEARCH-UNCITED)",
     _chk_research_cited),
    # 11th check — CLAIMS-WITHOUT-CITATION (AF-RESEARCH-UNCITED). If slide copy
    # contains factual/statistical claim markers (%, $, 'research', 'study', etc.)
    # and the research pack has zero cited URLs, the deck is shipping unsupported
    # claims. Uses rel sentinel None (needs the whole run dir to find both copy
    # and research pack).
    (None,
     "claims-without-citation — slide copy claim markers must have a cited research pack",
     "Phase -0.5 — Deep Research Specialist SOP 9.1/9.4 (AF-RESEARCH-UNCITED)",
     _chk_claims_without_citation),
    ("working/qc/copy_qc_report.json",
     "copy QC report (gate Phase 1Q, average >= 8.5, no AF-* triggered)",
     "Phase 1Q — QC Specialist SOP 9.1 / SOP-SLIDE-00",
     _chk_copy_qc),
    ("working/copy/arc_allocation.json",
     "converting arc — per-slide arc-section allocation",
     "Phase 3 — Signature Presentation Architect SOP",
     _chk_arc),
    ("working/copy/slides_copy.md",
     "slide copy authored per doctrine (hook >=7x, 10 components)",
     "Phase 4 — Slide Copywriter SOP",
     _chk_slides_copy),
    ("working/research/design-brief-*.md",
     "typography/design brief — per-slide creative art direction",
     "Phase F — Typography Architect / SOP-DESIGN-01/02",
     _chk_design_brief),
    # 7th check — ANTI-COMPRESSION coverage gate (AF-COVERAGE-1). The rel sentinel
    # None tells run_preflight to call this check with the run_dir itself (it needs
    # both mission_prd.json's source_slide_count AND the output slide count), not a
    # single resolved artifact path.
    (None,
     "anti-compression coverage — output slides >= client source_slide_count (Mode B ADD-only)",
     "Mission PRD — source_slide_count (Mode A=0 always passes)",
     _chk_coverage),
    # 8th check — RICH-PROMPT-REQUIRED gate (AF-P1). EVERY slide must have a
    # hand-authored rich prompt >= 1,500 chars in working/prompts/. Like coverage,
    # this needs the whole run dir (it counts slides AND reads every prompt file),
    # so it uses the rel sentinel None.
    (None,
     "rich per-slide prompt — every slide has a >=1,500-char prompt in working/prompts/ (rendered VERBATIM)",
     "Phase 2 — Slide Image Creator SOP 9.1 (15-element rich prompt; rendered verbatim, no thin fallback)",
     _chk_rich_prompts),
    # 9th check — SPEECH-LENGTH gate (AF-SPEECH-SHORT). Conditional: enforced only
    # once the presenter speech exists (it is written downstream at delivery), so it
    # never blocks the pre-speech render but is wired so it can't be silently skipped.
    (None,
     "speech length — presenter speech words >= target_talk_minutes x 120 wpm (fails short)",
     "Phase 9 — Presenter Speech Writer SOP 9.1 (130 wpm pacing; 120 wpm floor)",
     _chk_speech_length),
]


def find_run_dir(explicit: Optional[str], slides_path: Path, out_path: Path) -> Path:
    """Resolve the run/working dir: --run-dir, else first ancestor containing a
    `working/` subtree (searched from slides.json then out.pptx dir), else
    slides.json's parent."""
    if explicit:
        return Path(explicit).resolve()
    for start in (slides_path.resolve().parent, out_path.resolve().parent):
        cur = start
        for _ in range(8):  # bounded upward walk
            if (cur / "working").is_dir():
                return cur
            if cur.parent == cur:
                break
            cur = cur.parent
    return slides_path.resolve().parent


def resolve_logo_path(logo_arg: Optional[str], run_dir: Path) -> Optional[Path]:
    """Resolve the official logo PNG. Priority:
        1. --logo <png> flag (wins over everything).
        2. working/copy/intake.json -> brand.logo_image_path (relative paths are
           resolved against the run dir, then the intake.json's own directory).
    Returns an absolute Path to an existing file, or None if no logo is configured.
    FAILS LOUD (exit 2) if a logo IS configured but the file is missing/unreadable."""
    candidate = None
    source = None

    if logo_arg:
        candidate = Path(logo_arg).expanduser()
        source = f"--logo {logo_arg}"
    else:
        intake = run_dir / "working" / "copy" / "intake.json"
        if intake.exists():
            obj = _read_json(intake)
            if isinstance(obj, dict) and "__parse_error__" not in obj:
                brand = obj.get("brand") or {}
                raw = str((brand.get("logo_image_path") or "")).strip() if isinstance(brand, dict) else ""
                if raw:
                    p = Path(raw).expanduser()
                    if not p.is_absolute():
                        # try run_dir-relative first, then intake.json-relative
                        for base in (run_dir, intake.parent):
                            cand = (base / p)
                            if cand.exists():
                                p = cand
                                break
                    candidate = p
                    source = f"intake.json brand.logo_image_path ({raw})"

    if candidate is None:
        return None

    candidate = candidate.resolve()
    if not candidate.exists() or not candidate.is_file():
        print(f"FATAL: official logo configured via {source} but file not found: "
              f"{candidate}", file=sys.stderr)
        sys.exit(2)
    # Light sanity: must be a PNG (RGBA transparency is what we preserve).
    with open(candidate, "rb") as f:
        magic = f.read(8)
    if magic[:4] != b"\x89PNG":
        print(f"FATAL: official logo {candidate} is not a PNG "
              f"(magic={magic[:8].hex()}). Provide a PNG (RGBA preferred).",
              file=sys.stderr)
        sys.exit(2)
    return candidate


def run_preflight(run_dir: Path, slides_path: Optional[Path] = None) -> None:
    """Refuse (exit 3) unless every required upstream dept artifact exists AND is
    complete. Lists exactly what is missing and which dept phase/role produces it.

    H3: slides_path is the ACTUAL positional slides.json the renderer will render.
    Threading it into the run-dir-scoped checks (coverage, rich-prompts) makes those
    gates count the EXACT file that gets rendered, so the slide-count derived in
    preflight always matches what main() renders — closing the gate-bypass where
    preflight counted a different canonical slides.json than the one rendered."""
    import inspect as _inspect
    print(f"=== PROCESS PREFLIGHT — run dir: {run_dir} ===", flush=True)
    problems = []
    for rel, label, phase, check in PREFLIGHT_REQUIRED:
        if rel is None:
            # run-dir-scoped check (e.g. _chk_coverage needs the whole run dir). Pass
            # slides_path too when the checker accepts it (H3), so the slide-count
            # gates derive from the actual rendered file.
            try:
                accepts_slides = "slides_path" in _inspect.signature(check).parameters
            except (TypeError, ValueError):
                accepts_slides = False
            if accepts_slides:
                reason = check(run_dir, slides_path)
            else:
                reason = check(run_dir)
            display = "(coverage / anti-compression)"
        else:
            if "*" in rel:
                matches = sorted(run_dir.glob(rel))
                found = matches[0] if matches else None
            else:
                p = run_dir / rel
                found = p if p.exists() else None
            reason = check(found)
            display = rel
        if reason:
            problems.append((display, label, phase, reason))
        else:
            print(f"  OK   {display}", flush=True)

    if problems:
        print("\nFATAL: PROCESS PREFLIGHT FAILED — refusing to render or assemble.", file=sys.stderr)
        print("build_deck.py is only the deterministic renderer/assembler; it cannot", file=sys.stderr)
        print("produce a compliant deliverable without the upstream department artifacts.\n", file=sys.stderr)
        print(f"Run/working dir checked: {run_dir}", file=sys.stderr)
        print("Missing or incomplete required artifacts:\n", file=sys.stderr)
        for rel, label, phase, reason in problems:
            print(f"  - {rel}", file=sys.stderr)
            print(f"      what:    {label}", file=sys.stderr)
            print(f"      reason:  {reason}", file=sys.stderr)
            print(f"      produced by: {phase}", file=sys.stderr)
        print("\nFix: run the real Presentations department pipeline (which produces these),", file=sys.stderr)
        print("or, for deliberate standalone testing ONLY, re-run with --adhoc-no-process", file=sys.stderr)
        print("(its output is explicitly NOT a process-compliant deliverable).", file=sys.stderr)
        sys.exit(3)

    print("=== PREFLIGHT PASSED — upstream dept artifacts present ===\n", flush=True)


def print_adhoc_banner() -> None:
    bar = "!" * 78
    print(bar, flush=True)
    print("!! ADHOC MODE (--adhoc-no-process): PROCESS PREFLIGHT SKIPPED.", flush=True)
    print("!! The output of this run is NOT a process-compliant deliverable.", flush=True)
    print("!! No research / copy / QC / human-approval artifacts were verified.", flush=True)
    print("!! Use for standalone testing ONLY — never for client work.", flush=True)
    print(bar + "\n", flush=True)


def _sha256_file(path: Path) -> Optional[str]:
    """Return the sha256 hex digest of a file, or None if unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return None


def write_process_manifest(run_dir: Path, rendered, task_ids, model_used,
                           out_path: Path, timestamp: str) -> Path:
    """APPEND this render's record to working/checkpoints/process_manifest.json.

    The manifest is a cumulative, multi-phase record: each department phase appends
    its own entry under "phases" — this writer must NEVER clobber prior phases. It
    creates working/checkpoints/ and the JSON file if absent, then appends one
    "render" phase record carrying: KIE taskIds, the model used, per-slide image
    sha256 hashes, the output slide count, and the timestamp (passed in by the
    caller — this runs in a plain Python script, so os/Date use is fine here).

    Returns the manifest path. Append-safe: a corrupt/legacy file is preserved as a
    sibling .corrupt-<ts> backup rather than silently overwritten."""
    ckpt_dir = run_dir / "working" / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = ckpt_dir / "process_manifest.json"

    manifest = {"phases": []}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text())
            if isinstance(existing, dict):
                manifest = existing
                if not isinstance(manifest.get("phases"), list):
                    manifest["phases"] = []
            elif isinstance(existing, list):
                # legacy: a bare list of phase records — preserve it.
                manifest = {"phases": existing}
        except Exception:  # noqa: BLE001
            # Preserve the unreadable prior file instead of clobbering it.
            backup = manifest_path.with_suffix(
                f".corrupt-{timestamp.replace(':', '').replace('-', '')}")
            try:
                manifest_path.replace(backup)
            except Exception:  # noqa: BLE001
                pass
            manifest = {"phases": []}

    per_slide = []
    for r in rendered:
        f = r.get("file")
        per_slide.append({
            "slide": r.get("slide"),
            "taskId": r.get("taskId"),
            "image": f,
            "image_sha256": _sha256_file(Path(f)) if f else None,
        })

    record = {
        "phase": "render",
        "tool": "build_deck.py",
        "timestamp": timestamp,
        "model_used": model_used,
        "taskIds": list(task_ids),
        "output_slide_count": len(rendered),
        "output_pptx": str(out_path),
        "slides": per_slide,
    }
    manifest["phases"].append(record)

    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


# ---------------------------------------------------------------------------
# DELIVERABLES LEDGER — per-run deliverables.json (Requirements 2, 3)
# ---------------------------------------------------------------------------
# The ledger is written to <bundle_dir>/deliverables.json incrementally:
#   * initialised at the start of the run (all entries status=pending)
#   * updated after each artifact is produced (status=built or verified)
#   * finalised at the postflight gate (status=verified on pass, or unchanged
#     + hard-fail AF-BUNDLE-COMPLETE on failure)
#
# The final "complete" report is generated by READING deliverables.json
# (all entries verified), NOT from in-memory state. This survives crashes
# and supports resume: re-running the script re-reads the ledger and only
# re-checks artifacts that are not yet verified.
#
# IMPORTANT: this script builds only the deck_pptx. The other five artifacts
# are produced by upstream roles. The ledger records whatever state they are
# in when the postflight gate runs. If any are absent or below threshold the
# gate fails loud (AF-BUNDLE-COMPLETE, exit 5).

def _resolve_bundle_dir(out_dir_arg: Optional[str], out_path: Path) -> Path:
    """Resolve the final bundle dir.
       Priority: --out CLI arg > ~/Downloads/<deck-slug>/.
       The <deck-slug> is the stem of the out.pptx path (e.g. 'acme-q1' from
       'acme-q1.pptx').
    """
    if out_dir_arg:
        d = Path(out_dir_arg).expanduser().resolve()
    else:
        slug = out_path.stem or "deck"
        d = Path(BUNDLE_DIR_DEFAULT) / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _expand_filename(template: str, deck_slug: str) -> str:
    """Replace {deck_slug} placeholder in a filename template."""
    return template.replace("{deck_slug}", deck_slug)


def init_deliverables_ledger(bundle_dir: Path, deck_slug: str) -> Path:
    """Create or reset deliverables.json in bundle_dir with all artifacts
    set to status=pending. Returns the ledger path.

    If a ledger already exists and has verified entries, preserves them
    (supports resume: only re-checks non-verified artifacts)."""
    ledger_path = bundle_dir / "deliverables.json"
    existing = {}
    if ledger_path.exists():
        try:
            data = json.loads(ledger_path.read_text())
            if isinstance(data, list):
                existing = {e["key"]: e for e in data if isinstance(e, dict) and "key" in e}
        except Exception:  # noqa: BLE001
            existing = {}

    entries = []
    for spec in DELIVERABLES_REQUIRED:
        key = spec["key"]
        fname = _expand_filename(spec["filename"], deck_slug)
        # Preserve a prior verified entry so resume works.
        if key in existing and existing[key].get("status") == "verified":
            entries.append(existing[key])
        else:
            entries.append({
                "key": key,
                "filename": fname,
                "path": str(bundle_dir / fname),
                "label": spec["label"],
                "min_bytes": spec["min_bytes"],
                "note": spec["note"],
                "status": "pending",
                "size": None,
                "error": None,
            })
    ledger_path.write_text(json.dumps(entries, indent=2))
    return ledger_path


def update_deliverable_status(ledger_path: Path, key: str, status: str,
                               size: Optional[int] = None,
                               error: Optional[str] = None) -> None:
    """Update a single artifact entry in deliverables.json. status must be
    one of: pending | built | verified | failed.
    Writes the ledger to disk immediately (incremental, crash-safe)."""
    try:
        entries = json.loads(ledger_path.read_text())
    except Exception:  # noqa: BLE001
        return  # if the ledger is unreadable, skip silently (gate will catch it)
    for e in entries:
        if e.get("key") == key:
            e["status"] = status
            if size is not None:
                e["size"] = size
            if error is not None:
                e["error"] = error
            break
    ledger_path.write_text(json.dumps(entries, indent=2))


# ---------------------------------------------------------------------------
# C2 — POSTFLIGHT CONTENT-TYPE MAGIC-BYTE VERIFICATION
# ---------------------------------------------------------------------------
# The completeness gate used to check only exists() + size, so a symlink pointing
# at a large unrelated file, or a decoy file of the right size but the wrong type,
# would PASS. C2 hardens it: reject symlinks outright, size via os.lstat (never
# follow a link), and verify the file's leading magic bytes match the type implied
# by its extension. .md stays size-only (plain text has no magic signature).
#
# Map of deliverable key -> tuple of acceptable leading-byte signatures. A PPTX is a
# ZIP (Office Open XML), so it begins with the local-file-header magic 'PK\x03\x04'.
# An MP3 is either an ID3v2-tagged file ('ID3') or a raw MPEG frame sync ('\xff\xfb'
# / '\xff\xf3' / '\xff\xf2'). PNG begins with '\x89PNG'. PDF begins with '%PDF'.
DELIVERABLE_MAGIC = {
    "deck_pptx":       (b"PK\x03\x04",),                              # PPTX = ZIP (OOXML)
    "deck_pdf":        (b"%PDF",),
    "guide_pdf":       (b"%PDF",),
    "speech_pdf":      (b"%PDF",),
    "audio_mp3":       (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),  # ID3v2 tag or MPEG sync
    "infographic_png": (b"\x89PNG",),
    # teleprompter_html: a real HTML document leads with a doctype or an <html> /
    # <!-- ... --> opener. Accept the common case-variant openers so a legitimate
    # self-contained teleprompter page passes while a decoy of the wrong type fails.
    "teleprompter_html": (b"<!DOCTYPE", b"<!doctype", b"<!Doctype",
                          b"<html", b"<HTML", b"<!--"),
    # speech_md / speech_fish_md: intentionally absent — plain/tagged markdown has no
    # magic signature, so md stays size-only (per spec).
}


def _magic_ok(path: Path, signatures) -> bool:
    """Return True if the file's leading bytes match ANY of the given signatures.
    Reads only the bytes needed for the longest signature. HTML may carry a leading
    UTF-8 BOM (\\xef\\xbb\\xbf) or leading whitespace before the doctype/tag, so the
    comparison tolerates a BOM + leading whitespace for text-ish (non-binary) types."""
    try:
        want = max(len(s) for s in signatures)
        with open(path, "rb") as f:
            head = f.read(want + 8)  # +8 to cover an optional BOM + a little leading WS
    except OSError:
        return False
    if any(head.startswith(s) for s in signatures):
        return True
    # Tolerate a leading UTF-8 BOM and/or leading ASCII whitespace ONLY for text-ish
    # signatures (those beginning with '<'); binary magics (PNG/PDF/ZIP/MP3) must be
    # at byte 0 and are not relaxed.
    text_sigs = tuple(s for s in signatures if s[:1] == b"<")
    if text_sigs:
        trimmed = head
        if trimmed.startswith(b"\xef\xbb\xbf"):
            trimmed = trimmed[3:]
        trimmed = trimmed.lstrip(b" \t\r\n")
        if any(trimmed.startswith(s) for s in text_sigs):
            return True
    return False


def run_postflight_gate(bundle_dir: Path, ledger_path: Path, deck_slug: str) -> None:
    """POSTFLIGHT COMPLETENESS GATE (AF-BUNDLE-COMPLETE, Requirement 2).

    After assembly, verify EVERY DELIVERABLES_REQUIRED artifact exists in
    bundle_dir AND passes its min_bytes threshold. Updates deliverables.json
    with the verified/failed status for each artifact, then reads it back to
    produce the final report.

    If ANY artifact is missing or below threshold → prints a LOUD failure
    listing exactly which are missing + sys.exit(5). The script may print
    COMPLETE/DONE ONLY when all pass.

    The final "complete" report is generated by READING deliverables.json
    (all entries verified), NOT from in-memory state.
    """
    # --- Phase 1: scan and update each entry ---
    # C2: reject symlinks (a symlink to a large unrelated file would otherwise pass),
    # size via os.lstat (NEVER follow a link), and verify the leading magic bytes
    # match the type implied by the extension (a decoy of the right size but wrong
    # type is rejected). md stays size-only (plain text has no magic signature).
    missing_or_short = []
    for spec in DELIVERABLES_REQUIRED:
        key = spec["key"]
        fname = _expand_filename(spec["filename"], deck_slug)
        path = bundle_dir / fname
        # exists() follows symlinks; use lexists so a broken/dangling symlink is seen
        # as present-but-rejected rather than silently "absent".
        if not os.path.lexists(str(path)):
            update_deliverable_status(ledger_path, key, "failed",
                                      error="file absent from bundle_dir")
            missing_or_short.append((key, fname, spec["label"], spec["min_bytes"], 0,
                                     "ABSENT"))
            continue
        # C2: a symlink (or any non-regular file) is a decoy vector — reject it.
        if path.is_symlink():
            update_deliverable_status(ledger_path, key, "failed",
                                      error="path is a symlink (rejected: a symlink "
                                            "can point at a large unrelated/decoy file)")
            missing_or_short.append((key, fname, spec["label"], spec["min_bytes"], 0,
                                     "SYMLINK"))
            continue
        # os.lstat: size of the path itself, never a followed link.
        st = os.lstat(str(path))
        if not __import__("stat").S_ISREG(st.st_mode):
            update_deliverable_status(ledger_path, key, "failed",
                                      error="path is not a regular file (rejected)")
            missing_or_short.append((key, fname, spec["label"], spec["min_bytes"], 0,
                                     "NOT_REGULAR"))
            continue
        actual = st.st_size
        if actual < spec["min_bytes"]:
            update_deliverable_status(ledger_path, key, "failed",
                                      size=actual,
                                      error=f"file too small: {actual} bytes "
                                            f"(min {spec['min_bytes']})")
            missing_or_short.append((key, fname, spec["label"], spec["min_bytes"],
                                     actual, "UNDER_THRESHOLD"))
            continue
        # C2: magic-byte content-type check (md is intentionally size-only).
        signatures = DELIVERABLE_MAGIC.get(key)
        if signatures is not None and not _magic_ok(path, signatures):
            sig_disp = "/".join(repr(s) for s in signatures)
            update_deliverable_status(ledger_path, key, "failed",
                                      size=actual,
                                      error=f"wrong content type: leading bytes do not "
                                            f"match expected magic {sig_disp} for this "
                                            f"deliverable type (decoy/wrong-type file)")
            missing_or_short.append((key, fname, spec["label"], spec["min_bytes"],
                                     actual, "WRONG_TYPE"))
            continue
        update_deliverable_status(ledger_path, key, "verified", size=actual)

    # --- Phase 2: read ledger back as the authoritative final state ---
    try:
        ledger_entries = json.loads(ledger_path.read_text())
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: deliverables.json could not be read for final verification: {exc}",
              file=sys.stderr)
        sys.exit(5)

    all_verified = all(e.get("status") == "verified" for e in ledger_entries)

    # --- Phase 3: fail loud on any non-verified artifact ---
    if missing_or_short or not all_verified:
        bar = "=" * 78
        print(f"\n{bar}", file=sys.stderr)
        print("FATAL: POSTFLIGHT COMPLETENESS GATE FAILED (AF-BUNDLE-COMPLETE)", file=sys.stderr)
        print("build_deck.py produced the deck PPTX, but the required deliverable bundle",
              file=sys.stderr)
        print("is INCOMPLETE. The run may NOT be reported as 'complete' or 'done'.", file=sys.stderr)
        print(f"Bundle dir: {bundle_dir}", file=sys.stderr)
        print(f"Ledger:     {ledger_path}", file=sys.stderr)
        print("\nMissing or under-threshold artifacts:", file=sys.stderr)
        for (key, fname, label, min_b, actual_b, reason) in missing_or_short:
            if reason == "ABSENT":
                print(f"  MISSING  [{key}] {fname}  ({label})", file=sys.stderr)
                print(f"           Required by DELIVERABLES_REQUIRED; produced by upstream",
                      file=sys.stderr)
                print(f"           roles (presenter guide → Presenters Guide Specialist;",
                      file=sys.stderr)
                print(f"           speech → Presenters Speech Writer;",
                      file=sys.stderr)
                print(f"           audio → Audio Demonstration Specialist;",
                      file=sys.stderr)
                print(f"           infographic → infographic-checklist role;",
                      file=sys.stderr)
                print(f"           deck PDF → PPTX Assembly Specialist).",
                      file=sys.stderr)
            elif reason == "UNDER_THRESHOLD":
                print(f"  TOO SMALL [{key}] {fname}  ({label})", file=sys.stderr)
                print(f"           actual={actual_b:,} bytes  minimum={min_b:,} bytes",
                      file=sys.stderr)
            elif reason == "SYMLINK":
                print(f"  SYMLINK  [{key}] {fname}  ({label})", file=sys.stderr)
                print(f"           path is a symlink — rejected (a symlink can point at",
                      file=sys.stderr)
                print(f"           a large unrelated/decoy file to fake the size gate).",
                      file=sys.stderr)
            elif reason == "NOT_REGULAR":
                print(f"  NOT A FILE [{key}] {fname}  ({label})", file=sys.stderr)
                print(f"           path is not a regular file — rejected.", file=sys.stderr)
            elif reason == "WRONG_TYPE":
                print(f"  WRONG TYPE [{key}] {fname}  ({label})", file=sys.stderr)
                print(f"           actual={actual_b:,} bytes but leading magic bytes do",
                      file=sys.stderr)
                print(f"           not match the expected type (decoy / wrong-type file).",
                      file=sys.stderr)
            else:
                print(f"  TOO SMALL [{key}] {fname}  ({label})", file=sys.stderr)
                print(f"           actual={actual_b:,} bytes  minimum={min_b:,} bytes",
                      file=sys.stderr)
        # Also surface any ledger entries that are not verified but not in our scan list
        # (edge case: previously-failed entries from a prior run).
        extra_unverified = [e for e in ledger_entries
                            if e.get("status") != "verified"
                            and e.get("key") not in {m[0] for m in missing_or_short}]
        for e in extra_unverified:
            print(f"  NOT VERIFIED [{e['key']}] {e.get('filename')} — status: {e.get('status')}",
                  file=sys.stderr)
        print(f"\n{bar}", file=sys.stderr)
        sys.exit(5)

    # --- Phase 4: success — print COMPLETE only when ALL verified ---
    print("\n=== POSTFLIGHT COMPLETENESS GATE PASSED (AF-BUNDLE-COMPLETE) ===", flush=True)
    print(f"All {len(DELIVERABLES_REQUIRED)} required deliverables present and sized.",
          flush=True)
    print(f"Bundle dir: {bundle_dir}", flush=True)
    for e in ledger_entries:
        size_str = f"{e.get('size', 0):,} bytes" if e.get("size") else "n/a"
        print(f"  VERIFIED  [{e['key']}] {e.get('filename')}  ({size_str})", flush=True)
    print(f"Ledger (all-verified): {ledger_path}", flush=True)
    print("=== COMPLETE ===\n", flush=True)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[1:]

    # Pull out the flags (any position) before reading positional args.
    adhoc = False
    run_dir_arg = None
    logo_arg = None
    timestamp_arg = None
    out_dir_arg = None   # --out BUNDLE_DIR (default ~/Downloads/<deck-slug>)
    positional = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--adhoc-no-process":
            adhoc = True
        elif tok == "--run-dir":
            i += 1
            if i >= len(argv):
                print("FATAL: --run-dir requires a directory argument.", file=sys.stderr)
                sys.exit(2)
            run_dir_arg = argv[i]
        elif tok.startswith("--run-dir="):
            run_dir_arg = tok[len("--run-dir="):]
        elif tok == "--logo":
            i += 1
            if i >= len(argv):
                print("FATAL: --logo requires a PNG path argument.", file=sys.stderr)
                sys.exit(2)
            logo_arg = argv[i]
        elif tok.startswith("--logo="):
            logo_arg = tok[len("--logo="):]
        elif tok == "--timestamp":
            i += 1
            if i >= len(argv):
                print("FATAL: --timestamp requires a value.", file=sys.stderr)
                sys.exit(2)
            timestamp_arg = argv[i]
        elif tok.startswith("--timestamp="):
            timestamp_arg = tok[len("--timestamp="):]
        elif tok == "--out":
            i += 1
            if i >= len(argv):
                print("FATAL: --out requires a directory path argument.", file=sys.stderr)
                sys.exit(2)
            out_dir_arg = argv[i]
        elif tok.startswith("--out="):
            out_dir_arg = tok[len("--out="):]
        elif tok.startswith("--"):
            print(f"FATAL: unknown flag {tok!r}.", file=sys.stderr)
            sys.exit(2)
        else:
            positional.append(tok)
        i += 1

    if len(positional) not in (2, 3):
        print("Usage: python3 build_deck.py <slides.json> <out.pptx> [renders_dir] "
              "[--run-dir DIR] [--logo PNG] [--out BUNDLE_DIR] "
              "[--timestamp ISO8601] [--adhoc-no-process]",
              file=sys.stderr)
        sys.exit(2)

    slides_path = Path(positional[0])
    out_path = Path(positional[1])
    renders_dir = Path(positional[2]) if len(positional) == 3 else out_path.parent / "renders"

    # BUNDLE DIR + DELIVERABLES LEDGER (Requirements 3 & 4)
    # Must be resolved before any render so the ledger exists and can be updated
    # incrementally (crash-safe). The deck_slug is derived from the out.pptx stem.
    deck_slug = out_path.stem or "deck"
    bundle_dir = _resolve_bundle_dir(out_dir_arg, out_path)
    print(f"=== OUTPUT BUNDLE DIR (default ~/Downloads): {bundle_dir} ===", flush=True)
    ledger_path = init_deliverables_ledger(bundle_dir, deck_slug)
    print(f"=== DELIVERABLES LEDGER: {ledger_path} ===", flush=True)

    if not slides_path.exists():
        print(f"FATAL: slides.json not found: {slides_path}", file=sys.stderr)
        sys.exit(2)

    try:
        slides = json.loads(slides_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"FATAL: slides.json is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(slides, list) or not slides:
        print("FATAL: slides.json must be a non-empty JSON array.", file=sys.stderr)
        sys.exit(2)

    # Basic schema validation (deterministic, fail loud).
    seen = set()
    for s in slides:
        if not isinstance(s, dict):
            print("FATAL: every slide must be an object.", file=sys.stderr)
            sys.exit(2)
        for req in ("slide", "scene", "copy"):
            if req not in s:
                print(f"FATAL: slide missing required field '{req}': {json.dumps(s)}", file=sys.stderr)
                sys.exit(2)
        if not isinstance(s["copy"], list) or not s["copy"]:
            print(f"FATAL: slide {s.get('slide')}: 'copy' must be a non-empty array.", file=sys.stderr)
            sys.exit(2)
        ordn = s["slide"]
        if not isinstance(ordn, int) or ordn in seen:
            print(f"FATAL: slide ordinal must be a unique integer: {ordn}", file=sys.stderr)
            sys.exit(2)
        seen.add(ordn)

    # PROCESS PREFLIGHT (un-bypassable unless --adhoc-no-process). Runs BEFORE any
    # API key load, render, or assembly so a bypass costs zero KIE renders.
    run_dir = find_run_dir(run_dir_arg, slides_path, out_path)
    if adhoc:
        print_adhoc_banner()
    else:
        # H3: pass the ACTUAL positional slides.json so the coverage / rich-prompt
        # gates count the exact file that will be rendered (no gate-bypass via a
        # different canonical-path slides.json).
        run_preflight(run_dir, slides_path)

    # OFFICIAL-LOGO resolution: --logo wins; else intake.json brand.logo_image_path.
    # IMAGE-TO-IMAGE logo: if --logo is a URL, KIE composites the REAL logo via
    # input_urls (verified gpt-image-2-image-to-image). A local path falls back to a
    # flat overlay in assemble. Never resolve a URL as a local file.
    logo_url = logo_arg if (logo_arg and str(logo_arg).startswith("http")) else None
    if logo_url:
        # C1 (SSRF / local-file-read guard): the --logo URL is passed to KIE as an
        # input_urls reference and is otherwise fetchable. Enforce the http(s)
        # allowlist up front so a file://, ftp://, or data: --logo is refused before
        # any render. (startswith("http") already excludes most, but a value like
        # "httpx://" or "http\tfile://" would slip past a naive prefix check — the
        # urlparse scheme allowlist is the authoritative gate.)
        try:
            assert_url_scheme_allowed(logo_url, what="--logo URL")
        except ValueError as exc:
            print(f"FATAL: {exc}", file=sys.stderr)
            sys.exit(2)
    logo_path = None if logo_url else resolve_logo_path(logo_arg, run_dir)
    if logo_url:
        print(f"=== OFFICIAL LOGO (IMAGE-TO-IMAGE): {logo_url} — KIE composites the REAL "
              f"logo into EVERY slide via input_urls ===", flush=True)
    elif logo_path is not None:
        print(f"=== OFFICIAL LOGO (overlay fallback): {logo_path} ===", flush=True)

    api_key = load_api_key()
    renders_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== build_deck — {len(slides)} slides ===", flush=True)
    print(f"slides.json: {slides_path}", flush=True)
    print(f"renders_dir: {renders_dir}", flush=True)
    print(f"out.pptx:    {out_path}", flush=True)
    print(f"endpoint:    {CREATE_URL}  model={MODEL_T2I}\n", flush=True)

    rendered = []
    task_ids = []
    failures = []

    has_official_logo = (logo_path is not None) or (logo_url is not None)
    ordered = sorted(slides, key=lambda s: s["slide"])

    # PARALLEL RENDER: each slide is an independent KIE generation, so fan them out
    # across a bounded ThreadPoolExecutor. Per-slide retry / 429 backoff still live
    # inside render_slide; we just run the slides concurrently.
    workers = min(_render_workers(), len(ordered))
    print(f"=== rendering {len(ordered)} slides with {workers} parallel workers ===\n", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_slide = {
            pool.submit(render_slide, slide, api_key, renders_dir, run_dir,
                        has_official_logo=has_official_logo, logo_url=logo_url): slide
            for slide in ordered
        }
        for fut in concurrent.futures.as_completed(future_to_slide):
            slide = future_to_slide[fut]
            try:
                result = fut.result()
                rendered.append(result)
                task_ids.append(result["taskId"])
            except Exception as exc:  # noqa: BLE001
                failures.append({"slide": slide.get("slide"), "error": str(exc)})
                print(f"  SLIDE FAILED: {exc}", file=sys.stderr, flush=True)

    # Deterministic order for the summary / manifest regardless of completion order.
    rendered.sort(key=lambda r: r["slide"])
    task_ids = [r["taskId"] for r in rendered]
    failures.sort(key=lambda f: (f.get("slide") is None, f.get("slide")))

    # FAIL LOUD: never produce a partial deck silently.
    if failures:
        summary = {
            "slidesRendered": len(rendered),
            "kieTaskIds": task_ids,
            "outputPath": None,
            "failures": failures,
        }
        print("\n=== SUMMARY (FAILED) ===", file=sys.stderr)
        print(json.dumps(summary, indent=2))
        sys.exit(1)

    # PER-SLIDE SPEAKER NOTES: auto-discover + parse the presenter speech (if it
    # exists yet) so the assembled deck carries word-for-word notes per slide. This
    # is NON-FATAL — a phase-4 render usually precedes the phase-9 speech, so an
    # absent speech yields None and the deck is assembled with no notes. The speech
    # is NEVER required to render. Count mismatches are safe: extra chunks are simply
    # not matched to any slide; deck slides with no chunk get no notes part.
    speech_chunks = discover_speech_chunks(run_dir, bundle_dir)

    # Assemble.
    try:
        # When image-to-image baked the logo in (logo_url), do NOT also overlay it.
        assemble_pptx(rendered, out_path, logo_path=(None if logo_url else logo_path),
                      speech_chunks=speech_chunks)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: pptx assembly failed: {exc}", file=sys.stderr)
        summary = {
            "slidesRendered": len(rendered),
            "kieTaskIds": task_ids,
            "outputPath": None,
            "failures": [{"slide": "ASSEMBLY", "error": str(exc)}],
        }
        print(json.dumps(summary, indent=2))
        sys.exit(1)

    # Timestamp: caller-supplied --timestamp wins (lets the orchestrator pin a
    # consistent run clock); else stamp now. This is a plain Python script, so
    # using the local clock here is fine.
    timestamp = timestamp_arg or time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")

    # APPEND the render record to the cumulative process manifest (never clobber
    # prior phases) instead of leaving the result stdout-only.
    manifest_path = None
    try:
        manifest_path = write_process_manifest(
            run_dir, rendered, task_ids, MODEL_T2I, out_path, timestamp)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: render succeeded but process manifest write failed: {exc}",
              file=sys.stderr, flush=True)

    # DELIVERABLES LEDGER — mark the deck_pptx as built now that assembly succeeded.
    # The other five artifacts are produced by upstream roles; the postflight gate
    # will check their actual presence on disk.
    pptx_size = out_path.stat().st_size if out_path.exists() else 0
    update_deliverable_status(ledger_path, "deck_pptx", "built", size=pptx_size)

    # If the out_path is not inside bundle_dir, copy the pptx into bundle_dir so the
    # postflight gate finds it at its expected location.
    bundle_pptx = bundle_dir / f"{deck_slug}-FINAL.pptx"
    if out_path.resolve() != bundle_pptx.resolve():
        import shutil
        try:
            shutil.copy2(str(out_path), str(bundle_pptx))
            update_deliverable_status(ledger_path, "deck_pptx", "built",
                                      size=bundle_pptx.stat().st_size)
            print(f"=== PPTX copied to bundle dir: {bundle_pptx} ===", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: could not copy PPTX to bundle_dir: {exc}", file=sys.stderr)

    summary = {
        "slidesRendered": len(rendered),
        "kieTaskIds": task_ids,
        "outputPath": str(out_path),
        "bundleDir": str(bundle_dir),
        "deliverables_ledger": str(ledger_path),
        "modelUsed": MODEL_T2I,
        "timestamp": timestamp,
        "processManifest": str(manifest_path) if manifest_path else None,
        "failures": [],
    }
    print("\n=== SUMMARY (RENDER OK — running postflight completeness gate) ===",
          flush=True)
    print(json.dumps(summary, indent=2))

    # POSTFLIGHT COMPLETENESS GATE (Requirement 2 — AF-BUNDLE-COMPLETE).
    # This is the FINAL gate: exit 0 only when ALL nine bundle deliverables are
    # present and sized. Exit 5 (loud failure) when any are missing or under-threshold.
    # The word "COMPLETE" / "DONE" is printed ONLY from inside run_postflight_gate
    # after reading deliverables.json (not from in-memory state).
    run_postflight_gate(bundle_dir, ledger_path, deck_slug)
    sys.exit(0)


if __name__ == "__main__":
    main()
