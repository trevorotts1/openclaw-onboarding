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
speech PDF, the presenter audio (PRESENTER-AUDIO.mp3), the deck PDF export, the
infographic checklist slide, or the GHL media upload. The FULL deliverable downstream
is the FIVE-FILE bundle —
    [Deck-Title]-FINAL.pptx, [Deck-Title]-FINAL.pdf, PRESENTER-GUIDE.pdf,
    PRESENTER-SPEECH.pdf, PRESENTER-AUDIO.mp3
— PLUS the infographic checklist slide IN the deck PLUS a recorded/verified GHL media
upload. The .pptx this script emits is an INTERMEDIATE artifact. The Director/Delivery
flow MUST run the guide / speech / audio / PDF / infographic / GHL roles, and the run
is blocked from "Done" by the DELIVERY INTERLOCK (AF-DELIVER + AF-DH1 +
AF-DELIVERY-COMPLETE). Do NOT "finish at a .pptx." See
sops/CLIENT-WEBINAR-DECK-SOP.md §9a, sops/delivery-concierge-sops.md SOP 9.5, and
sops/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md (AF-DELIVERY-COMPLETE).
================================================================================

This is the PROVEN deterministic deck pipeline, generalized for the fleet. It is the
single-command, zero-AI-at-runtime path that takes a slides.json (the agent's only
creative output) and produces a finished .pptx with no further model judgement.

WHAT IT DOES (zero AI judgement at runtime):
    1. Reads a slides.json (see slides.schema.json) and an output .pptx path.
    2. For EACH slide, composes a KIE.ai text-to-image prompt MECHANICALLY by concatenating:
         scene description  +  exact English copy (verbatim from slides.json)  +
         optional logo wordmark + layout hint  +  the MANDATORY English/Latin-only pin.
       No model decides wording — the copy is whatever the slides.json author wrote.
       TWO prompt-side QC gates run on every slide, both FAIL-LOUD (no silent render):
         (a) FACIAL-INTELLIGENCE / REPRESENTATION gate — refuses any slide whose spec
             carries a forbidden hardcoded demographic default (the "60/30/10" landmine).
             Representation comes from the slide spec (the client's captured audience),
             never a baked-in default split (SOP-CAST-01, AF-R3).
         (b) CHAR-COUNT gate — the composed prompt length must be within
             [PROMPT_CHAR_FLOOR, PROMPT_CHAR_CEILING]; the 18,000 ceiling is the
             universal GPT-Image 2 safety boundary (AF-P1/AF-P2).
    3. Calls KIE.ai (gpt-image-2-text-to-image) per the ONLY-allowed recipe:
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
        [--logo PNG] [--adhoc-no-process]

    renders_dir defaults to "<out.pptx dir>/renders".

    NOTE: a successful run (exit 0 + a .pptx at <out.pptx>) means the deck is
    RENDERED, not DELIVERED. The .pptx alone is NOT a delivered presentation — the
    full five-file bundle + infographic checklist slide + GHL upload are required
    downstream (see the banner above and the DELIVERY INTERLOCK).

OFFICIAL-LOGO COMPOSITING (optional):
    --logo <png>  — path to the client's REAL, official logo PNG. When supplied
        (or when working/copy/intake.json carries brand.logo_image_path), the
        builder does TWO things so the deck wears the client's actual mark, not an
        AI-hallucinated wordmark:
          (1) compose_prompt instructs KIE to leave a CLEAN, EMPTY logo zone in the
              top-right corner and to render NO brand wordmark / logo text at all
              (the AI wordmark is SUPPRESSED — slides[].logo is ignored for the
              prompt when a real logo is in play).
          (2) assemble_pptx composites the EXACT same logo PNG (RGBA, transparency
              preserved) onto EVERY slide in a consistent top-right corner at a
              tasteful size (~13% of slide width) with a small margin, layered over
              the full-bleed background.
        The --logo flag wins over intake.json brand.logo_image_path if both exist.

PROCESS PREFLIGHT (un-bypassable by default):
    Before ANY render or assembly, build_deck.py REQUIRES that the upstream
    department process artifacts already exist on disk in the run/working dir.
    build_deck.py is ONLY the deterministic Phase-4 renderer + a stripped Phase-8
    assembler; it carries none of the upstream intelligence (research, copy,
    human approvals) or QC gates. Running it on a hand-fed slides.json with no
    upstream chain produces a technically-valid .pptx that NEVER went through the
    department flow — exactly the shortcut this preflight exists to refuse.

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
    0 — every slide rendered and the .pptx was written.
    1 — one or more slides failed after retries (NO .pptx written), or assembly failed.
    2 — fatal config error (no API key, bad slides.json, missing python-pptx, etc.).
    3 — process preflight FAILED: required upstream dept artifacts are missing
        (NO render, NO .pptx). Run the real dept pipeline, or pass
        --adhoc-no-process for explicit non-deliverable standalone testing.

ENVIRONMENT:
    KIE_API_KEY — the CLIENT's own KIE.ai key (never the operator's, never shared).
    Read from env, else from one of the client's standard env stores:
        ~/.openclaw/workspace/.env
        ~/clawd/secrets/.env
        ~/.openclaw/secrets/.env
    (paths expanded against the current user's HOME).
"""

import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

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
# 45-design-intelligence-library/library/_system/MODEL-SPECS.md):
#   * GPT-Image 2 hard ceiling on input.prompt is 20,000 characters on both
#     endpoints. The HARD MAXIMUM is 18,000 — a 2,000-char safety margin below
#     that ceiling so a prompt is never rejected or truncated by the platform.
#     This ceiling is UNIVERSAL: it applies to every prompt path, including this
#     deterministic one. A prompt over it is an AF-P2 auto-fail.
#   * The webinar pipeline's specificity FLOOR is 5,000 chars (AF-P1), but that
#     floor is for the long, specificity-rich prompts the Slide Image Creator
#     hand-writes in the full webinar pipeline. This deterministic builder composes a
#     MINIMAL mechanical prompt (scene + verbatim copy + pin), which is correctly
#     ~1,000 chars; imposing the 5,000 webinar floor here would reject every
#     valid deterministic prompt. So this path uses a low non-empty floor that
#     only catches a degenerate (empty / near-empty) composed prompt, while the
#     18,000 ceiling is enforced identically to the webinar path.
PROMPT_CHAR_FLOOR = 200       # deterministic-minimal floor (catches degenerate/empty prompts)
PROMPT_CHAR_CEILING = 18000   # UNIVERSAL hard maximum (AF-P2; 2,000 under the 20,000 API ceiling)

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
# Prompt composition — PURELY MECHANICAL (no AI)
# ---------------------------------------------------------------------------

def assert_no_forbidden_demographic_default(slide: dict) -> None:
    """
    FACIAL-INTELLIGENCE / REPRESENTATION GATE (fail-loud).

    Representation must come from the slide spec (the client's captured audience),
    never from a baked-in default split. Per SOP-CAST-01 ("there is no system
    default demographic") and AF-R3 ("no racial or gender default is ever
    inferred"), this deterministic builder REFUSES any slide whose scene / copy /
    layout / logo text smuggles a forbidden demographic-default landmine (e.g. the
    "60/30/10" ratio). Raises ValueError (caller fails the slide loud) on a hit.
    """
    # Gather every author-supplied text field on this slide into one haystack.
    chunks = [str(slide.get("scene", "")), str(slide.get("layout", "")),
              str(slide.get("logo", ""))]
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
                f"the client's captured audience in the slide spec, never a baked-in "
                f"default split (SOP-CAST-01 / AF-R3). Refusing to render."
            )


def compose_prompt(slide: dict, has_official_logo: bool = False) -> str:
    """
    Deterministically build the KIE prompt for one slide by concatenating, in order:
      scene  ->  exact copy lines (verbatim)  ->  logo  ->  layout  ->  English pin.
    No wording is invented; every text token comes straight from slides.json.

    OFFICIAL-LOGO mode (has_official_logo=True): the client's REAL logo PNG will be
    composited onto every slide in assemble_pptx. So this prompt MUST NOT ask KIE to
    render any brand wordmark / logo (the AI wordmark is suppressed — slide['logo']
    is ignored for the prompt), and instead instructs KIE to keep a CLEAN, EMPTY
    top-right corner zone so the real logo lands cleanly with nothing behind it.

    Two prompt-side QC gates run here, both fail-loud:
      * FACIAL-INTELLIGENCE gate: reject any forbidden demographic-default landmine
        (the 60/30/10 split) — representation comes from the slide spec, never a
        baked-in default (SOP-CAST-01 / AF-R3).
      * CHAR-COUNT gate: the composed prompt length must be within
        [PROMPT_CHAR_FLOOR, PROMPT_CHAR_CEILING]; outside = ValueError (AF-P1/AF-P2,
        18,000 ceiling is the universal GPT-Image 2 safety boundary).
    """
    # Prompt-side representation gate (before composing anything).
    assert_no_forbidden_demographic_default(slide)

    scene = str(slide["scene"]).strip()
    copy_lines = [str(c).strip() for c in slide["copy"] if str(c).strip()]
    if not copy_lines:
        raise ValueError(f"slide {slide.get('slide')}: 'copy' has no non-empty lines.")

    headline = copy_lines[0]
    rest = copy_lines[1:]

    layout = str(slide.get("layout", "")).strip()
    if not layout:
        layout = (
            "headline in the upper area, remaining copy in the lower third, "
            "high-contrast legible placement against the background"
        )

    logo = str(slide.get("logo", "")).strip()

    parts = []
    parts.append(f"A 16:9 presentation slide background. SCENE: {scene}")
    # The copy is rendered AS TEXT into the image — quote it verbatim so the model
    # spells it exactly.
    parts.append(f'Render this exact headline text on the slide, spelled exactly: "{headline}".')
    if rest:
        joined = " | ".join(f'"{line}"' for line in rest)
        parts.append(
            f"Also render this exact supporting copy, each on its own line, "
            f"spelled exactly: {joined}."
        )
    if has_official_logo:
        # IMAGE-TO-IMAGE: the client's REAL logo is supplied to KIE as a reference
        # image (input_urls). Instruct the model to place that EXACT provided logo
        # cleanly in the top-right corner — reproduce it faithfully, never redraw,
        # recolor, restyle, or invent a wordmark.
        parts.append(
            "Incorporate the PROVIDED brand logo (the supplied reference image) into "
            "the TOP-RIGHT CORNER of the slide, at a small, tasteful size with clear "
            "margin. Reproduce that exact logo faithfully — do NOT redraw, recolor, "
            "restyle, distort, or replace it, and do NOT invent any other wordmark, "
            "brand name, monogram, or emblem anywhere in the image. Only the provided "
            "logo appears, and only in that corner."
        )
    elif logo:
        parts.append(
            f'Render a small, clean brand wordmark reading exactly "{logo}" as a logo lockup.'
        )
    parts.append(f"LAYOUT: {layout}.")
    parts.append(
        "TYPOGRAPHY & DESIGN — make this a striking, magazine-grade EDITORIAL slide, "
        "NOT flat text on a photo: bold, expressive typography with strong scale "
        "contrast between the headline and supporting copy; a confident, intentional, "
        "editorial layout using weight, size, and negative space; the headline is a "
        "large, dramatic focal element. Premium color and contrast so the text pops "
        "off the scene. Keep every letter crisp, perfectly legible, fully inside the "
        "safe area, never cropped."
    )
    parts.append(ENGLISH_PIN)

    prompt = " ".join(parts)

    # Self-guard: never let the dead endpoint string sneak into a prompt payload.
    if DEAD_ENDPOINT_FRAGMENT in prompt:
        raise ValueError(
            f"slide {slide.get('slide')}: composed prompt contains the dead endpoint "
            f"fragment '{DEAD_ENDPOINT_FRAGMENT}'. Refusing."
        )

    # PROMPT CHAR-COUNT GATE (fail-loud): never render a degenerate (near-empty)
    # prompt, and never exceed the universal 18,000 hard ceiling (AF-P1/AF-P2).
    length = len(prompt)
    if length < PROMPT_CHAR_FLOOR:
        raise ValueError(
            f"slide {slide.get('slide')}: composed prompt is {length} chars, under the "
            f"floor of {PROMPT_CHAR_FLOOR}. The scene/copy is too thin to render a real "
            f"slide. Refusing (prompt char-count gate, AF-P1 floor)."
        )
    if length > PROMPT_CHAR_CEILING:
        raise ValueError(
            f"slide {slide.get('slide')}: composed prompt is {length} chars, over the "
            f"hard ceiling of {PROMPT_CHAR_CEILING} (2,000 under the 20,000 GPT-Image 2 API "
            f"ceiling, MODEL-SPECS). The scene/copy is too long; trim slides.json. Refusing "
            f"(prompt char-count gate, AF-P2 ceiling)."
        )
    return prompt


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class RateLimited(Exception):
    pass


def _http_json(method: str, url: str, api_key: str, body: Optional[dict] = None) -> dict:
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

def render_slide(slide: dict, api_key: str, renders_dir: Path,
                 has_official_logo: bool = False, logo_url: Optional[str] = None) -> dict:
    """
    Render a single slide. Returns {"slide", "file", "taskId"} on success.
    Raises RuntimeError if all SLIDE_MAX_ATTEMPTS fail.
    """
    ordinal = int(slide["slide"])
    name = f"slide-{ordinal:02d}"
    out_path = renders_dir / f"{name}.png"
    prompt = compose_prompt(slide, has_official_logo=has_official_logo)

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


def assemble_pptx(rendered: list, out_path: Path, logo_path: Optional[Path] = None) -> None:
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


def _chk_intake(path: Optional[Path]) -> str:
    if path is None:
        return "file absent"
    obj = _read_json(path)
    if "__parse_error__" in obj:
        return f"not valid JSON ({obj['__parse_error__']})"
    if obj.get("interview_confirmed") is not True:
        return "interview_confirmed is not true"
    mode = str(obj.get("presentation_mode", "")).strip().lower()
    if mode not in ("one-person", "general"):
        return f"presentation_mode must be 'one-person' or 'general' (got {obj.get('presentation_mode')!r})"
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
    gate = str(obj.get("gate", "")).strip()
    if gate and gate != "Phase 1Q":
        return f"gate is {gate!r}, expected 'Phase 1Q'"
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
    if obj.get("pass") is False:
        return "report explicitly marks pass:false"
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


def _count_output_slides(run_dir: Path) -> Optional[int]:
    """Count the slides the system is about to output. Prefer slides.json (the
    deterministic renderer's direct input); fall back to arc_allocation.json's
    per-slide allocation. Returns None when neither can be read."""
    # 1. slides.json — the renderer's direct input. Look in a few canonical spots.
    for rel in ("working/copy/slides.json", "slides.json", "working/slides.json"):
        p = run_dir / rel
        if p.exists():
            obj = _read_json(p)
            if isinstance(obj, list):
                return len(obj)
            if isinstance(obj, dict) and "__parse_error__" not in obj:
                slides = obj.get("slides")
                if isinstance(slides, list):
                    return len(slides)
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


def _chk_coverage(run_dir: Path) -> str:
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

    final = _count_output_slides(run_dir)
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


def run_preflight(run_dir: Path) -> None:
    """Refuse (exit 3) unless every required upstream dept artifact exists AND is
    complete. Lists exactly what is missing and which dept phase/role produces it."""
    print(f"=== PROCESS PREFLIGHT — run dir: {run_dir} ===", flush=True)
    problems = []
    for rel, label, phase, check in PREFLIGHT_REQUIRED:
        if rel is None:
            # run-dir-scoped check (e.g. _chk_coverage needs the whole run dir).
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
# main
# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[1:]

    # Pull out the flags (any position) before reading positional args.
    adhoc = False
    run_dir_arg = None
    logo_arg = None
    timestamp_arg = None
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
        elif tok.startswith("--"):
            print(f"FATAL: unknown flag {tok!r}.", file=sys.stderr)
            sys.exit(2)
        else:
            positional.append(tok)
        i += 1

    if len(positional) not in (2, 3):
        print("Usage: python3 build_deck.py <slides.json> <out.pptx> [renders_dir] "
              "[--run-dir DIR] [--logo PNG] [--timestamp ISO8601] [--adhoc-no-process]",
              file=sys.stderr)
        sys.exit(2)

    slides_path = Path(positional[0])
    out_path = Path(positional[1])
    renders_dir = Path(positional[2]) if len(positional) == 3 else out_path.parent / "renders"

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
        run_preflight(run_dir)

    # OFFICIAL-LOGO resolution: --logo wins; else intake.json brand.logo_image_path.
    # IMAGE-TO-IMAGE logo: if --logo is a URL, KIE composites the REAL logo via
    # input_urls (verified gpt-image-2-image-to-image). A local path falls back to a
    # flat overlay in assemble. Never resolve a URL as a local file.
    logo_url = logo_arg if (logo_arg and str(logo_arg).startswith("http")) else None
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
    for slide in sorted(slides, key=lambda s: s["slide"]):
        try:
            result = render_slide(slide, api_key, renders_dir,
                                  has_official_logo=has_official_logo, logo_url=logo_url)
            rendered.append(result)
            task_ids.append(result["taskId"])
        except Exception as exc:  # noqa: BLE001
            failures.append({"slide": slide.get("slide"), "error": str(exc)})
            print(f"  SLIDE FAILED: {exc}", file=sys.stderr, flush=True)

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

    # Assemble.
    try:
        # When image-to-image baked the logo in (logo_url), do NOT also overlay it.
        assemble_pptx(rendered, out_path, logo_path=(None if logo_url else logo_path))
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

    summary = {
        "slidesRendered": len(rendered),
        "kieTaskIds": task_ids,
        "outputPath": str(out_path),
        "modelUsed": MODEL_T2I,
        "timestamp": timestamp,
        "processManifest": str(manifest_path) if manifest_path else None,
        "failures": [],
    }
    print("\n=== SUMMARY (OK) ===", flush=True)
    print(json.dumps(summary, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
