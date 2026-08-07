#!/usr/bin/env python3
"""
workbook_builder.py — FEATURE L2-D: fillable PDF workbook for the Presentations department.

Every presentation gets a branded, fillable PDF workbook. This executor:

  [1] DESIGN — generates each page background via kie.ai gpt-image-2
      (gpt-image-2-text-to-image for page 1 / the brand template; gpt-image-2-image-to-image
      for later pages, referencing page 1 + the client brand render for harmony). Prompts
      are 5,000-19,000 chars (author to >=9,000 target). Background-only: no text baked —
      the real form content is overlaid as AcroForm fields in step [2]. Parallel submit
      within the 20/10s rate limit, then poll and download each render.
  [2] ASSEMBLE — reportlab draws each PNG full-bleed (center-crop-to-fill) onto a US Letter
      page (612x792 pt) and overlays AcroForm fields from a per-page field manifest.
      CRITICAL gotcha: c.acroForm.extras["NeedAppearances"] = "true" (string literal, NOT
      Python True — a Python bool serializes as "True" and corrupts the PDF).
  [3] VERIFY — pypdf reads back the field count + page count.
  [4] UPLOAD — posts the workbook PDF to GHL via the shared ghl_media path (operator account
      for tests; never a client).

RULES
  * Never print a credential value. KIE_API_KEY is read like kie_generate.py (env first,
    then the client's standard secrets stores).
  * Model sovereignty: gpt-image-2 ONLY (gpt-image-2-text-to-image / gpt-image-2-image-to-image).
  * No browser / no UI automation for GHL — only the REST path.
  * This is NOT the deck renderer. It does NOT touch build_deck.py. It does NOT assemble
    PPTX. It produces ONE additional deliverable: the fillable workbook PDF.

USAGE
    python3 scripts/workbook_builder.py --run-dir <run_dir> [--out <path>] [--pages 3]
                                        [--manifest <workbook.json>] [--skip-design] [--no-upload]

    --run-dir    The governed pipeline run dir (reads working/copy/intake.json + renders/).
    --out        Output PDF path (default <run_dir>/working/deliverables/<deck_slug>-WORKBOOK.pdf)
    --pages      Number of workbook pages to design+assemble (default 3).
    --manifest   Optional workbook.json manifest (page list + field manifests). When absent,
                 a DEFAULT 3-page workbook is generated (Cover / My Goals / Action Plan).
    --skip-design  Reuse already-downloaded page PNGs (working/workbook/pages/) without a
                 fresh kie.ai run. Assembly + verify + upload only.
    --no-upload    Skip the GHL upload step (assembly + verify only).
    --selftest   Deterministic offline self-test (no network, no reportlab render spend).

EXIT CODES
    0 — workbook built (+ verified; uploaded unless --no-upload)
    1 — one or more pages failed to render/download
    2 — fatal configuration error (no API key, bad manifest, missing deps)
    3 — verification failed (pypdf did not read back fields / page count)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Kie.ai constants (RESEARCH doc / Skill 07 / Skill 46 — exact strings)
# ---------------------------------------------------------------------------
CREATE_URL = "https://api.kie.ai/api/v1/jobs/createTask"
POLL_URL   = "https://api.kie.ai/api/v1/jobs/recordInfo"

MODEL_T2I = "gpt-image-2-text-to-image"
MODEL_I2I = "gpt-image-2-image-to-image"

ASPECT_RATIO = "3:4"
RESOLUTION   = "2K"

RATE_CAP_REQUESTS = 20          # kie.ai: 20 new tasks / 10 seconds / account
RATE_CAP_WINDOW_S = 10.0

INITIAL_POLL_WAIT_S = 20        # first poll delay after all submits (small workbook)
POLL_INTERVAL_S     = 10
MAX_POLL_PASSES     = 90        # ~15 min cap per task

DEAD_ENDPOINT_FRAGMENT = "/api/v1/image/gpt-image"

# prompt band (research doc §4.1): 5,000-19,000 stripped chars; target >=9,000
PROMPT_FLOOR = 5000
PROMPT_TARGET_MIN = 9000
PROMPT_CEILING = 19000

# ---------------------------------------------------------------------------
# Reportlab constants
# ---------------------------------------------------------------------------
PAGE_WIDTH_PT  = 612.0   # US Letter
PAGE_HEIGHT_PT = 792.0

NEED_APPEARANCES = "true"   # STRING literal. reportlab serializes a Python True as "True".

# Brand defaults when intake carries no palette (used only as a fallback).
DEFAULT_PRIMARY   = "#212748"   # deep navy (deck brand default)
DEFAULT_SECONDARY = "#B38456"   # gold (deck brand accent)
DEFAULT_ACCENT    = "#C49A70"   # warm gold
DEFAULT_BASE      = "#F2E6D7"   # warm cream
DEFAULT_INK       = "#1A1A1A"


# ---------------------------------------------------------------------------
# Shared prompt-gate (optional import; degrade to minimal inline checks)
# ---------------------------------------------------------------------------
def _load_prompt_gate():
    try:
        import importlib
        import prompt_gate
        return prompt_gate
    except Exception:  # noqa: BLE001
        return None


prompt_gate = _load_prompt_gate()


def _secrets_candidates() -> list:
    candidates = []
    override = os.environ.get("OPENCLAW_SECRETS", "").strip()
    if override:
        candidates.append(os.path.expanduser(override))
    candidates += [
        os.path.expanduser("~/.openclaw/workspace/.env"),
        os.path.expanduser("~/clawd/secrets/.env"),
        os.path.expanduser("~/.openclaw/secrets/.env"),
    ]
    return candidates


def _load_api_key() -> str:
    key = os.environ.get("KIE_API_KEY", "").strip()
    if key:
        return key.strip("'\"")
    for path in _secrets_candidates():
        p = Path(path)
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line.startswith("KIE_API_KEY="):
                value = line[len("KIE_API_KEY="):].strip().strip("'\"")
                if value:
                    return value
    raise RuntimeError(
        "KIE_API_KEY not found in environment or any secrets store — cannot design workbook pages. "
        "Set KIE_API_KEY (or $OPENCLAW_SECRETS at the client's .env)."
    )


# ---------------------------------------------------------------------------
# HTTP helpers (mirror kie_generate.py's proven transport, incl. FIX-6 AuthError)
# ---------------------------------------------------------------------------
class AuthError(RuntimeError):
    """Permanent auth failure (401/403) — never retry, never re-submit."""


def _http_json(method: str, url: str, api_key: str, body: Optional[dict] = None,
               timeout: int = 30) -> dict:
    if DEAD_ENDPOINT_FRAGMENT in url:
        raise RuntimeError(
            f"REFUSED: attempted to call the dead endpoint {DEAD_ENDPOINT_FRAGMENT}. "
            "This script only uses /api/v1/jobs/createTask and /api/v1/jobs/recordInfo."
        )
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        if exc.code in (401, 403):
            raise AuthError(
                f"HTTP {exc.code} {method} {url}\nResponse: {body_text}\n"
                "Permanent auth failure — do NOT re-submit. Check the KIE_API_KEY."
            ) from exc
        raise RuntimeError(f"HTTP {exc.code} {method} {url}\nResponse: {body_text}") from exc


# ---------------------------------------------------------------------------
# Brand / intake helpers
# ---------------------------------------------------------------------------
def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return {}


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


def resolve_brand(run_dir: Path) -> Dict[str, str]:
    """Brand palette from intake.json (brand.palette) or a design brief, else defaults."""
    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    brand = intake.get("brand") if isinstance(intake.get("brand"), dict) else {}
    palette = brand.get("palette") if isinstance(brand.get("palette"), dict) else {}
    out = {
        "primary":   _hex_color(palette.get("primary"), DEFAULT_PRIMARY),
        "secondary": _hex_color(palette.get("secondary"), DEFAULT_SECONDARY),
        "accent":    _hex_color(palette.get("accent"), DEFAULT_ACCENT),
        "base":      _hex_color(palette.get("base"), DEFAULT_BASE),
        "ink":       _hex_color(palette.get("ink"), DEFAULT_INK),
    }
    # Fallback: derive from a design brief (design-brief-*.md) — grep for hex codes.
    brief = _first_hex_from_design_brief(run_dir)
    if brief:
        out["primary"] = brief.get("primary", out["primary"])
    return out


def _first_hex_from_design_brief(run_dir: Path) -> Dict[str, str]:
    """Best-effort: pull the first 6-hex tokens from a design brief for the primary."""
    brief_dir = run_dir / "working" / "research"
    if not brief_dir.is_dir():
        return {}
    for f in sorted(brief_dir.glob("design-brief-*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        hexes = re.findall(r"#[0-9a-fA-F]{6}\b", text)
        if hexes:
            return {"primary": _hex_color(hexes[0], DEFAULT_PRIMARY)}
    return {}


def resolve_deck_slug(run_dir: Path) -> str:
    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    slug = intake.get("deck_slug") or run_dir.name
    return str(slug).strip() or "presentation"


def resolve_client_name(run_dir: Path) -> str:
    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    for key in ("client_name", "company", "business_name", "name"):
        v = intake.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return resolve_deck_slug(run_dir).replace("-", " ").title()


# ---------------------------------------------------------------------------
# Prompt template (Section-4 template from WORKBOOK-PAGE-PROMPT-TEMPLATE.md)
# ---------------------------------------------------------------------------
def build_page_prompt(*, page_role: str, motif_position: str, brand: Dict[str, str],
                      client_name: str, is_i2i: bool, page_index: int,
                      page_count_total: int = 3) -> str:
    """Compose a >=9,000-char (target) background-only page prompt."""
    prim, sec, acc = brand["primary"], brand["secondary"], brand["accent"]
    base, ink = brand["base"], brand["ink"]

    style_ref = (
        "\n=== STYLE REFERENCE DIRECTIVE ===\n"
        "Use the attached images only as style reference for color grading, lighting, and "
        "composition — do not copy their subjects, faces, or text.\n"
    ) if is_i2i else ""

    prompt = f"""[ARCHETYPE CLEAN-BRANDED-WORKBOOK-SHELL]
DESIGN A PRINTABLE WORKBOOK PAGE BACKGROUND, PORTRAIT, US-LETTER-8.5x11 EQUIVALENT (3:4 ASPECT).

This is the BACKGROUND ONLY for a fillable PDF form page in a client workbook. Generate the
visual shell — NO words, NO labels, NO numbers, NO placeholder content anywhere. All form
content will be overlaid later as crisp, real form fields (11pt body, 14pt field labels,
24pt page titles on a 612x792pt US-Letter composition grid). The page must read as a premium,
clean, professionally-branded worksheet with clearly reserved EMPTY ZONES for those fields.

=== BRAND LOCKUP ===
Client: {client_name}. Industry: professional services. Grade: premium, calm, trustworthy.
Brand palette (use these EXACT hex values, no substitutions):
  Primary: {prim} — header band and footer rule only.
  Secondary: {sec} — section accent bands and thin rules.
  Accent: {acc} — one small geometric motif (thin corner brace or small circle) only.
  Base: {base} (near-white) — page background and every field-zone interior.
  Ink: {ink} (near-black) — very light hairline rules, at most 8% opacity.
Typography character: clean geometric sans (Montserrat-like), used only as a visual system —
no visible text. Type-size tokens for the future overlay: 24pt page title, 14pt section
labels, 11pt body text, all Helvetica-compatible geometric sans; these sizes are the grid
reference the AcroForm overlay will honor, never baked glyphs.
Logo treatment: the {client_name} wordmark appears ONLY as a LOW-OPACITY watermark in the
footer band, ~14% opacity, left-aligned, ~2.5in wide. Do not place it anywhere else.
(On the image-to-image path, the real page-1 reference is attached — preserve its palette,
lighting, and composition; do not copy any baked text.)

=== LAYOUT GRID (fixed per page) ===
The page divides top-to-bottom into three bands, composed on a strict thirds grid:
  HEADER BAND (top 0-15%): a solid {prim} color block, or a clean flat header with a thin
    {acc} underline rule at its bottom edge. Empty and quiet — reserved for the page title
    and a client-name form line. Header height is 15% of the 2688px page height (~403px).
  FIELD BAND (15-85%): on {base}. Contains ONLY the empty field zones described below.
    Flat, even color. No patterns, no photos, no gradients that fight text. This band is the
    working grid: three even horizontal rows (top, middle, lower) with generous negative
    space and 0.6in safe margins on all four sides.
  FOOTER BAND (85-100%): a hairline rule in {sec}, the low-opacity wordmark watermark at
    left, and an EMPTY rectangular zone at bottom-right reserved for a page-number form
    field.
Safe margins: 0.6in on all four sides. Nothing touches the edges.

=== EMPTY FIELD ZONES (reserve exactly these; each a clean flat shape, no content) ===
1. Header-right: one wide rounded-rectangle zone, {sec} at 8% tint, ~4.5in wide x 0.5in
   tall — reserved for a client-name text field. Quiet, no shading inside.
2. Field band, top row: three evenly spaced empty box rows, each {sec} at 5% tint with a
   thin {sec} bottom rule, ~6.5in wide x 0.6in tall each — reserved for short-answer lines.
   The interior of each must be plain, uniform, empty.
3. Field band, middle: two larger empty panels side by side, ~3.1in wide x 2.2in tall each,
   plain {base} with a thin {sec} border and softly rounded corners — reserved for
   check-list / short-note zones. Interiors empty and uniform.
4. Field band, bottom-left: one large empty notes panel ~4.2in wide x 3.0in tall, plain
   {base} with a thin {sec} border — reserved for a long-answer multiline field. Interior
   empty.
This page's workbook role is {page_role}; vary zone emphasis only in the direction of that
role (e.g. a Weekly Check-In page may widen zone 3). Leave every zone CLEAR and VISUALLY
QUIET for text overlay. Do not decorate inside any zone. The zones are placed on the thirds
grid (upper third, center third, lower third) with safe margins honored so no field ever
collides with the header or footer band.

=== MOTIF (consistent every page, small) ===
One small {acc} geometric motif per page, placed at {motif_position}. It is decorative only,
thin-line, never over a field zone. Motif is a hairline corner brace or a single small
circle, no more than 1in across, kept at least 0.8in from every field zone.

=== DO-NOT BLOCK (negative directives, exhaustive) ===
No text, no words, no letters, no numbers, no labels, no placeholder glyphs, no characters,
no people, no hands, no fused hands, no fingers, no faces, no malformed anatomy, no
distorted facial features, no mismatched eyes, no asymmetric eyes, no distorted teeth, no
over-smoothed skin, no body-proportion errors, no extra limbs, no photos, no busy textures,
no high-detail backgrounds, no gradients crossing a field zone, no shadows over any field
zone, no watermark over any field zone, no watermark in the header, no clip-art, no clutter,
no noise, no vignetting over the field band. Flat, clean, minimal, corporate. Do not write
any words inside the reserved zones. Do not draw letters in any font. No misspelled or
garbled words anywhere (there must be no words to garble). Do not redraw, recolor, restyle,
or reinterpret the attached reference brand mark. No emoji, no clipart, no default-font UI
artifacts, no pure-black fills, no em-dash typographic artifacts, no system-default fonts.
No narration of the image, no presenter lines, no stage directions, no webinar or
telegraphing language, no "describe the picture" captions, no bracketed placeholder tokens,
no TBD/owner-to-confirm/pending inserts. No demographic defaults, no skin-tone directives,
no lightening or desaturation of any cast — representation is not a subject of this render.
The reference mark must be rendered exactly as attached, letter-for-letter and shape-for-shape,
never redrawn.

=== QUALITY ===
Crisp 2K edges, flat clean vector-flat aesthetic, professional corporate workbook page,
extremely high information density of DESIGN (not content), soft even tone, consistent with
the attached reference page. Portrait 3:4 at 2K resolution (2016x2688px). Do not crop or
letterbox. Uniform lighting, no competing visual firsts, generous negative space so the
overlaid form text (11pt-14pt) always reads at high contrast on the field zones.

=== DETERMINISTIC VARIANT (page {page_index} of {page_count_total}) ===
This is page {page_index} of a {page_count_total}-page workbook. To keep the set feeling
designed rather than stamped, rotate exactly ONE subtle accent placement per page:
  - page 1: accent motif top-right, header is a solid primary band;
  - page 2: accent motif bottom-left, header is a flat primary block with a thin accent rule;
  - page 3: accent motif above the footer rule, header keeps the thin accent underline;
  - later pages cycle through the same three motif positions in order (top-right,
    bottom-left, above-footer) so no two adjacent pages share a motif position.
Nothing else rotates: the palette, the band structure, the field-zone geometry, the
watermark, and the footer rule are identical on every page. The variation is a one-element
flex, never a layout change and never a new decorative element.

=== PAGE-ROLE ART DIRECTION (page {page_index} of the workbook) ===
This workbook page is: {page_role}.
It is part of a branded fillable workbook for {client_name}. The role determines only which
field zone is emphasized and the header band's visual weight:
  - For a Cover page: the header band is the strongest element (full primary band, thin
    accent rule at its base); the rest of the page is quiet with a single wide notes panel
    in the lower third.
  - For a Goals / Planning page: the top-row short-answer lines (zone 2) and the two side
    panels (zone 3) carry the page; the notes panel is secondary.
  - For an Action Plan / Checklist page: the three short-answer lines dominate the upper
    third; the lower third holds a single wide commitment panel.
  - For a Weekly Check-In / Progress page: widen zone 3 (the two side panels) and keep the
    notes panel at the standard size.
In every case the header band stays at {prim}, the field band stays on {base}, the footer
band keeps the {sec} hairline rule and the {client_name} watermark, and the {acc} motif sits
at {motif_position}. No page role changes the palette, the margins, the band structure, or
the empty-zone discipline. The emphasis is a shift of zone weight only, never an added
element, never a baked word, never a photo.

=== DESIGN SYSTEM RECAP (locked every page, repeat verbatim) ===
Header band color: {prim}. Footer rule color: {sec}. Motif color: {acc}. Field-zone border
color: {sec}. Field-zone interior: {base}. Page background: {base}. Hairlines: {ink} at 8%.
All edges straight or softly rounded (max 8px radius). No drop shadows, no inner shadows, no
glow, no gradients across any zone, no vignette, no noise, no paper grain. The design reads
as one system across every page: same palette, same band ratios, same motif language, same
watermark placement. The 2K raster must be crisp and non-tiled, filling the full 3:4 frame
edge to edge with no letterbox bars.
{style_ref}"""
    return prompt


def _assert_prompt_band(prompt: str, page_id: str) -> None:
    """Enforce the 5,000-19,000 stripped-char band (target >=9,000). Raise on violation."""
    stripped = prompt.strip()
    n = len(stripped)
    if n < PROMPT_FLOOR:
        raise RuntimeError(
            f"{page_id}: prompt is {n} chars, UNDER the {PROMPT_FLOOR}-char floor. "
            "A workbook page prompt below the floor is a thin stub — not submitted.")
    if n > PROMPT_CEILING:
        raise RuntimeError(
            f"{page_id}: prompt is {n} chars, OVER the {PROMPT_CEILING}-char ceiling. "
            "Tighten redundant phrasing.")
    if prompt_gate is not None:
        try:
            prompt_gate.verify_prompt(prompt, slide_id=page_id)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"{page_id}: shared prompt gate rejected the workbook page: {exc}")


# ---------------------------------------------------------------------------
# kie.ai submit / poll / download (submit-all-then-wait, rate-limited)
# ---------------------------------------------------------------------------
def submit_page(page: dict, api_key: str) -> str:
    """Submit ONE workbook page to createTask; return taskId."""
    mode = str(page.get("mode", "i2i")).lower()
    model = MODEL_I2I if mode == "i2i" else MODEL_T2I
    prompt = page["prompt"]
    urls = page.get("input_urls") or []

    if prompt_gate is not None:
        try:
            prompt_gate.verify_prompt(prompt, slide_id=page.get("id"))
            prompt_gate.check_mode_consistency(model, urls,
                                               logo_bearing=bool(page.get("logo_bearing")),
                                               slide_id=page.get("id"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"{page.get('id')}: prompt gate: {exc}")
    elif mode == "i2i" and not urls:
        raise ValueError(f"{page.get('id')}: mode=i2i requires at least one input_urls entry.")

    input_block: dict = {
        "prompt": prompt,
        "aspect_ratio": page.get("aspect_ratio", ASPECT_RATIO),
        "resolution": page.get("resolution", RESOLUTION),
    }
    if mode == "i2i":
        input_block["input_urls"] = urls

    payload = {"model": model, "input": input_block}
    resp = _http_json("POST", CREATE_URL, api_key, body=payload)
    if resp.get("code") != 200:
        raise RuntimeError(f"{page.get('id')}: createTask non-200: {json.dumps(resp)}")
    task_id = (resp.get("data") or {}).get("taskId")
    if not task_id:
        raise RuntimeError(f"{page.get('id')}: createTask 200 but no taskId: {json.dumps(resp)}")
    return str(task_id)


def poll_task(task_id: str, api_key: str) -> str:
    """Poll recordInfo until success/fail; return resultUrls[0]."""
    for attempt in range(MAX_POLL_PASSES):
        resp = _http_json("GET", f"{POLL_URL}?taskId={task_id}", api_key)
        data = resp.get("data", {})
        state = str(data.get("state", "")).lower()
        if state == "success":
            rj = data.get("resultJson")
            if not rj:
                raise RuntimeError(f"taskId {task_id}: success but resultJson missing")
            urls = (json.loads(rj) or {}).get("resultUrls", [])
            if not urls:
                raise RuntimeError(f"taskId {task_id}: resultUrls empty")
            return urls[0]
        if state in ("fail", "failed", "error", "cancelled"):
            raise RuntimeError(f"taskId {task_id}: terminal state {state}: "
                               f"{data.get('failCode')} {data.get('failMsg')}")
        print(f"  [{attempt+1}/{MAX_POLL_PASSES}] {task_id}: {state} — sleeping {POLL_INTERVAL_S}s", flush=True)
        time.sleep(POLL_INTERVAL_S)
    raise RuntimeError(f"taskId {task_id}: exceeded {MAX_POLL_PASSES} poll passes")


def download(url: str, dest: Path) -> None:
    """Download a KIE result URL (no Bearer — the temp CDN 403s on auth)."""
    req = urllib.request.Request(url, headers={"User-Agent": "kie_generate/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
            f.write(resp.read())
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Download failed for {url}: {exc}") from exc
    with open(dest, "rb") as f:
        if f.read(4) != b"\x89PNG":
            raise RuntimeError(f"Downloaded {dest.name} is not a PNG (magic bytes mismatch)")


def design_pages(pages: list, api_key: str, pages_dir: Path) -> List[str]:
    """Design all workbook pages.

    TWO-PHASE strategy (harmony-first, per the research doc):
      Phase A — submit + download every T2I page FIRST (page 1 = the brand template page,
        no reference needed). The first T2I page's resultUrl becomes the brand harmony
        reference for every I2I page.
      Phase B — submit every I2I page referencing that page-1 URL (+ any existing render
        record URLs), rate-limited to 20/10s, then poll + download all.

    Returns the ordered list of downloaded PNG paths. Raises if ANY page fails.
    """
    pages_dir.mkdir(parents=True, exist_ok=True)
    n = len(pages)
    print(f"\n=== kie.ai workbook design — {n} pages (harmony-first two-phase) ===")

    t2i = [p for p in pages if str(p.get("mode", "i2i")).lower() != "i2i"]
    i2i = [p for p in pages if str(p.get("mode", "i2i")).lower() == "i2i"]
    if not t2i:
        # Every page is i2i (no brand template page): reference the deck's own renders.
        t2i = [pages[0]]
        t2i[0]["mode"] = "t2i"

    # ---- Phase A: brand template page(s) (t2i) ----
    phase_a_paths: Dict[str, str] = {}
    if t2i:
        print(f"\n--- Phase A: {len(t2i)} brand template page(s) (t2i) ---")
        task_map: Dict[str, dict] = {}
        for pg in t2i:
            try:
                tid = submit_page(pg, api_key)
                task_map[tid] = pg
                print(f"  SUBMITTED {pg['id']} -> {tid}", flush=True)
            except AuthError as exc:
                print(f"FATAL: {exc}", file=sys.stderr)
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"  SUBMIT ERROR {pg['id']}: {exc}", file=sys.stderr)
                pg["_submit_error"] = str(exc)
        if not task_map:
            raise RuntimeError("no Phase-A (brand template) page submitted successfully")
        print(f"  Waiting {INITIAL_POLL_WAIT_S}s before polling Phase A...")
        time.sleep(INITIAL_POLL_WAIT_S)
        ref_url: Optional[str] = None
        for tid, pg in task_map.items():
            dest = pages_dir / f"{pg['id']}.png"
            try:
                url = poll_task(tid, api_key)
                download(url, dest)
                print(f"  DOWNLOADED {pg['id']} -> {dest} ({dest.stat().st_size:,} bytes)", flush=True)
                phase_a_paths[pg["id"]] = str(dest)
                if ref_url is None:
                    ref_url = url
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL {pg['id']}: {exc}", file=sys.stderr)
                pg["_poll_error"] = str(exc)
        if len(phase_a_paths) != len(t2i):
            failed = [p["id"] for p in t2i if "_submit_error" in p or "_poll_error" in p]
            raise RuntimeError(f"Phase-A design incomplete: failed {failed}")

    # ---- Phase B: harmony pages (i2i) referencing page-1 URL ----
    phase_b_paths: Dict[str, str] = {}
    if i2i:
        print(f"\n--- Phase B: {len(i2i)} harmony page(s) (i2i) ---")
        # reference set: page-1 resultUrl + any render-record URLs
        base_refs = [ref_url] if ref_url else []
        # i2i pages need input_urls before submit; build from the page-1 URL.
        task_map = {}
        for idx, pg in enumerate(i2i):
            refs = base_refs[:]
            extra = pg.get("input_urls") or []
            for e in extra:
                if e not in refs:
                    refs.append(e)
            if not refs:
                raise RuntimeError(f"{pg['id']}: i2i page has no reference URL — submit page 1 "
                                   "(t2i) first, or pass input_urls in the manifest.")
            pg["input_urls"] = refs[:16]
            try:
                tid = submit_page(pg, api_key)
                task_map[tid] = pg
                print(f"  SUBMITTED {pg['id']} -> {tid} (refs={len(refs)})", flush=True)
            except AuthError as exc:
                print(f"FATAL: {exc}", file=sys.stderr)
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"  SUBMIT ERROR {pg['id']}: {exc}", file=sys.stderr)
                pg["_submit_error"] = str(exc)
            if (idx + 1) % RATE_CAP_REQUESTS == 0 and idx + 1 < len(i2i):
                print(f"  sleeping {RATE_CAP_WINDOW_S}s (rate cap window)...", flush=True)
                time.sleep(RATE_CAP_WINDOW_S)
        if not task_map:
            raise RuntimeError("no Phase-B (harmony) page submitted successfully")
        print(f"  Waiting {INITIAL_POLL_WAIT_S}s before polling Phase B...")
        time.sleep(INITIAL_POLL_WAIT_S)
        for tid, pg in task_map.items():
            dest = pages_dir / f"{pg['id']}.png"
            try:
                url = poll_task(tid, api_key)
                download(url, dest)
                print(f"  DOWNLOADED {pg['id']} -> {dest} ({dest.stat().st_size:,} bytes)", flush=True)
                phase_b_paths[pg["id"]] = str(dest)
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL {pg['id']}: {exc}", file=sys.stderr)
                pg["_poll_error"] = str(exc)

    # ---- ordered output ----
    out_paths: List[str] = []
    for pg in pages:
        p = phase_a_paths.get(pg["id"]) or phase_b_paths.get(pg["id"])
        if p:
            out_paths.append(p)
    if len(out_paths) != n:
        failed = [p["id"] for p in pages if "_submit_error" in p or "_poll_error" in p]
        raise RuntimeError(f"workbook design incomplete: {len(out_paths)}/{n} pages OK; "
                           f"failed: {failed}")
    return out_paths
    return out_paths


# ---------------------------------------------------------------------------
# Default 3-page workbook manifest (field manifests in IMAGE px; image is 2016x2688)
# ---------------------------------------------------------------------------
def default_workbook_manifest(client_name: str, brand: Dict[str, str]) -> Dict[str, Any]:
    """A sensible 3-page workbook: Cover / My Goals / Action Plan. Field coords are in the
    design image's pixel space (2016x2688); assembly maps px->pt (scale + y-flip)."""
    pages = [
        {
            "id": "page-01-cover",
            "page_role": "Cover",
            "mode": "t2i",
            "motif_position": "top-right",
            "fields": [
                {"name": "ClientName", "type": "text", "x": 1080, "y": 240,
                 "w": 760, "h": 90, "flags": "", "label": "Client Name"},
                {"name": "SessionDate", "type": "text", "x": 1080, "y": 380,
                 "w": 500, "h": 90, "flags": "", "label": "Date"},
                {"name": "CoachName", "type": "text", "x": 1080, "y": 520,
                 "w": 500, "h": 90, "flags": "", "label": "Coach"},
            ],
        },
        {
            "id": "page-02-goals",
            "page_role": "My Goals",
            "mode": "i2i",
            "motif_position": "bottom-left",
            "fields": [
                {"name": "Goal1", "type": "text", "x": 220, "y": 560, "w": 1576, "h": 110,
                 "flags": "", "label": "Goal 1"},
                {"name": "Goal2", "type": "text", "x": 220, "y": 760, "w": 1576, "h": 110,
                 "flags": "", "label": "Goal 2"},
                {"name": "Goal3", "type": "text", "x": 220, "y": 960, "w": 1576, "h": 110,
                 "flags": "", "label": "Goal 3"},
                {"name": "Why1", "type": "textarea", "x": 220, "y": 1180, "w": 720, "h": 420,
                 "flags": "multiline", "label": "Why this matters"},
                {"name": "Why2", "type": "textarea", "x": 1076, "y": 1180, "w": 720, "h": 420,
                 "flags": "multiline", "label": "How I will get there"},
            ],
        },
        {
            "id": "page-03-actions",
            "page_role": "Action Plan",
            "mode": "i2i",
            "motif_position": "above-footer",
            "fields": [
                {"name": "Action1", "type": "text", "x": 220, "y": 560, "w": 1576, "h": 110,
                 "flags": "", "label": "Action 1"},
                {"name": "Action2", "type": "text", "x": 220, "y": 760, "w": 1576, "h": 110,
                 "flags": "", "label": "Action 2"},
                {"name": "Action3", "type": "text", "x": 220, "y": 960, "w": 1576, "h": 110,
                 "flags": "", "label": "Action 3"},
                {"name": "Commitment", "type": "textarea", "x": 220, "y": 1180, "w": 1576,
                 "h": 420, "flags": "multiline", "label": "My commitment"},
            ],
        },
    ]
    return {
        "client_name": client_name,
        "brand": brand,
        "page_count": len(pages),
        "pages": pages,
    }


# ---------------------------------------------------------------------------
# Assembly (reportlab) — full-bleed center-crop-to-fill + AcroForm overlay
# ---------------------------------------------------------------------------
def _pt_from_px(x_px: float, w_px: float, pw: float) -> float:
    return x_px / w_px * pw


def _pt_y_from_px(y_px: float, h_px: float, ph: float) -> float:
    """Image top-down pixel coord -> PDF y (bottom-up, points)."""
    return ph - (y_px / h_px) * ph


def _field_flag_list(flags: str) -> List[str]:
    return [f.strip() for f in str(flags).split(",") if f.strip()]


def assemble_workbook(manifest: Dict[str, Any], page_pngs: List[str], out_path: Path,
                      brand: Dict[str, str]) -> int:
    """Build the fillable PDF. Returns field count."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from PIL import Image

    pw, ph = letter  # 612 x 792
    field_count = 0

    c = canvas.Canvas(str(out_path), pagesize=letter)
    # CRITICAL: string literal 'true', NOT Python True (reportlab serializes True as "True").
    c.acroForm.extras["NeedAppearances"] = NEED_APPEARANCES

    for page_spec, png_path in zip(manifest["pages"], page_pngs):
        img = Image.open(png_path)
        img_w, img_h = img.size
        img.close()

        # center-crop-to-fill: scale so the image covers the full letter page
        scale = max(pw / img_w, ph / img_h)
        iw, ih = img_w * scale, img_h * scale
        c.drawImage(str(png_path), (pw - iw) / 2, (ph - ih) / 2, width=iw, height=ih)

        for f in page_spec.get("fields", []):
            ftype = f.get("type", "text")
            name = f["name"]
            x_pt = _pt_from_px(f["x"], img_w, pw)
            y_pt = _pt_y_from_px(f["y"], img_h, ph)
            w_pt = f.get("w", 400) / img_w * pw
            h_pt = f.get("h", 60) / img_h * ph
            flags = _field_flag_list(f.get("flags", ""))
            bcol = HexColor(brand["primary"])

            if ftype in ("text", "textarea"):
                fflags = "multiline" if "multiline" in flags else ""
                if fflags:
                    c.acroForm.textfield(
                        name=name, value="", x=x_pt, y=y_pt, width=w_pt, height=h_pt,
                        borderWidth=1, borderColor=bcol, borderStyle="solid",
                        fontSize=11, forceBorder=True, fieldFlags=fflags)
                else:
                    c.acroForm.textfield(
                        name=name, value="", x=x_pt, y=y_pt, width=w_pt, height=h_pt,
                        borderWidth=1, borderColor=bcol, borderStyle="solid",
                        fontSize=11, forceBorder=True)
            elif ftype == "checkbox":
                size = min(w_pt, h_pt)
                c.acroForm.checkbox(name=name, x=x_pt, y=y_pt, size=size,
                                    borderColor=bcol, borderWidth=1,
                                    buttonStyle="check", checked=False)
            elif ftype in ("choice", "listbox"):
                options = f.get("options") or []
                # reportlab 4.4.10 choice() raises UnboundLocalError on empty value:
                # pass a non-empty default so the option list still lands.
                default = options[0] if options else ""
                c.acroForm.choice(name=name, value=default, options=options,
                                  x=x_pt, y=y_pt, width=w_pt, height=h_pt,
                                  borderWidth=1, borderColor=bcol, borderStyle="solid",
                                  fontSize=11, forceBorder=True)
            else:
                raise ValueError(f"unknown field type {ftype!r} for {name}")
            field_count += 1

        c.showPage()

    c.save()
    return field_count


# ---------------------------------------------------------------------------
# Verification (pypdf)
# ---------------------------------------------------------------------------
def verify_pdf(path: Path, expected_pages: int, expected_fields: int) -> Dict[str, Any]:
    """Read the PDF back with pypdf; confirm page count + fields + NeedAppearances."""
    from pypdf import PdfReader
    r = PdfReader(str(path))
    pages = len(r.pages)
    fields = r.get_fields() or {}
    needs_appearances = False
    try:
        needs_appearances = bool(r.trailer["/Root"]["/AcroForm"]["/NeedAppearances"])
    except Exception:  # noqa: BLE001
        needs_appearances = False
    return {
        "pages": pages,
        "fields": len(fields),
        "field_names": sorted(fields.keys()),
        "need_appearances": needs_appearances,
        "bytes": path.stat().st_size,
        "expected_pages": expected_pages,
        "expected_fields": expected_fields,
    }


# ---------------------------------------------------------------------------
# GHL upload (shared ghl_media path — operator account for tests)
# ---------------------------------------------------------------------------
def upload_workbook(pdf_path: Path, run_dir: Path, deck_slug: str) -> dict:
    """Upload the workbook PDF to the GHL media library via the shared ghl_media module.
    Reads client LOCATION PIT via resolve_location_pit / resolve_location_id (never the
    operator's key). The workbook PDF is a non-deck media artifact (not named *-FINAL.pdf),
    so it flows through the canonical upload with require_png=False."""
    import sys as _sys
    here = Path(__file__).resolve().parent
    if str(here) not in _sys.path:
        _sys.path.insert(0, str(here))
    import ghl_media
    pit = ghl_media.resolve_location_pit()
    location_id = ghl_media.resolve_location_id()
    name = f"{deck_slug}-WORKBOOK.pdf"
    # require_png=False: a PDF is not a PNG; existence is checked by the canonical call.
    res = ghl_media.upload_media(str(pdf_path), location_id, name, pit,
                                 require_png=False, run_dir=run_dir)
    return {
        "workbook_ghl_url": res["url"],
        "workbook_ghl_file_id": res["fileId"],
        "workbook_ghl_remote_name": name,
        "uploaded_at": _now_iso(),
    }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_ledger(run_dir: Path, record: dict) -> None:
    ledger = run_dir / "working" / "checkpoints" / "workbook.json"
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
    ap = argparse.ArgumentParser(description="Build the fillable PDF workbook "
                                             "(kie.ai gpt-image-2 backgrounds + reportlab AcroForm).")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--manifest", default=None, help="workbook.json manifest path")
    ap.add_argument("--skip-design", action="store_true",
                    help="reuse working/workbook/pages/ PNGs; assemble+verify+upload only")
    ap.add_argument("--no-upload", action="store_true", help="skip the GHL upload")
    ap.add_argument("--selftest", action="store_true", help="offline deterministic self-test")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.run_dir:
        ap.error("--run-dir is required (or --selftest)")
    run_dir = Path(args.run_dir).resolve()

    # --- brand + slug + client ---
    brand = resolve_brand(run_dir)
    deck_slug = resolve_deck_slug(run_dir)
    client_name = resolve_client_name(run_dir)

    pages_dir = run_dir / "working" / "workbook" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # --- manifest ---
    if args.manifest and Path(args.manifest).exists():
        manifest = _read_json(Path(args.manifest))
    else:
        manifest = default_workbook_manifest(client_name, brand)
    manifest.setdefault("brand", brand)
    manifest.setdefault("client_name", client_name)

    pages = manifest["pages"]
    if args.pages:
        pages = pages[: args.pages]
        manifest["pages"] = pages
        manifest["page_count"] = len(pages)

    # --- design (unless skipped) ---
    if not args.skip_design:
        api_key = _load_api_key()
        for i, pg in enumerate(pages):
            pg.setdefault("aspect_ratio", ASPECT_RATIO)
            pg.setdefault("resolution", RESOLUTION)
            is_i2i = str(pg.get("mode", "i2i")).lower() == "i2i"
            pg["prompt"] = build_page_prompt(
                page_role=pg.get("page_role", f"Page {i+1}"),
                motif_position=pg.get("motif_position", "top-right"),
                brand=brand, client_name=client_name, is_i2i=is_i2i,
                page_index=i + 1, page_count_total=len(pages))
            _assert_prompt_band(pg["prompt"], pg["id"])
        # design_pages resolves the harmony reference itself: phase A renders the t2i
        # brand-template page first, then feeds its resultUrl to every i2i page.
        page_pngs = design_pages(pages, api_key, pages_dir)
    else:
        missing = [p for p in pages if not (pages_dir / f"{p['id']}.png").exists()]
        if missing:
            print(f"FATAL: --skip-design but {len(missing)} page PNG(s) missing: {missing}",
                  file=sys.stderr)
            return 2
        page_pngs = [str(pages_dir / f"{p['id']}.png") for p in pages]

    # --- assemble ---
    out_path = Path(args.out) if args.out else \
        run_dir / "working" / "deliverables" / f"{deck_slug}-WORKBOOK.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Assembling fillable PDF -> {out_path} ===")
    field_count = assemble_workbook(manifest, page_pngs, out_path, brand)
    print(f"Assembled {len(page_pngs)} page(s), {field_count} AcroForm field(s).")

    # --- verify ---
    v = verify_pdf(out_path, len(page_pngs), field_count)
    print("\n=== pypdf verification ===")
    print(json.dumps(v, indent=2))
    if v["pages"] != len(page_pngs):
        print(f"FATAL: expected {len(page_pngs)} pages, pypdf read {v['pages']}", file=sys.stderr)
        return 3
    if v["fields"] < 1:
        print("FATAL: pypdf read zero AcroForm fields — form did not survive.", file=sys.stderr)
        return 3
    if not v["need_appearances"]:
        print("FATAL: /NeedAppearances not set (reportlab string-literal gotcha).", file=sys.stderr)
        return 3

    record = {
        "deck_slug": deck_slug,
        "workbook_pdf": str(out_path),
        "workbook_pdf_bytes": v["bytes"],
        "workbook_pages": v["pages"],
        "workbook_fields": v["fields"],
        "workbook_field_names": v["field_names"],
        "need_appearances": v["need_appearances"],
        "status": "built+verified",
        "built_at": _now_iso(),
    }
    _record_ledger(run_dir, record)

    # --- upload ---
    if not args.no_upload:
        print("\n=== Uploading to GHL (shared ghl_media path) ===")
        try:
            up = upload_workbook(out_path, run_dir, deck_slug)
            print(json.dumps(up, indent=2))
            record["status"] = "built+verified+uploaded"
            record.update(up)
            _record_ledger(run_dir, record)
        except Exception as exc:  # noqa: BLE001
            print(f"GHL UPLOAD FAILED (workbook still built+verified): {exc}", file=sys.stderr)
            record["status"] = "built+verified+upload_failed"
            record["upload_error"] = str(exc)
            _record_ledger(run_dir, record)
            return 1

    print("\nWORKBOOK BUILD: DONE")
    return 0


# ---------------------------------------------------------------------------
# Offline deterministic self-test (no network, no kie spend)
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails = []
    here = Path(__file__).resolve().parent

    # 1) prompt band: build a prompt, confirm 5,000-19,000 and full-rich-gate pass.
    brand = {"primary": DEFAULT_PRIMARY, "secondary": DEFAULT_SECONDARY,
             "accent": DEFAULT_ACCENT, "base": DEFAULT_BASE, "ink": DEFAULT_INK}
    p = build_page_prompt(page_role="My Goals", motif_position="top-right", brand=brand,
                          client_name="Test Client", is_i2i=True, page_index=1,
                          page_count_total=3)
    if not (PROMPT_FLOOR <= len(p.strip()) <= PROMPT_CEILING):
        fails.append(f"prompt band: {len(p.strip())} chars outside {PROMPT_FLOOR}-{PROMPT_CEILING}")
    if prompt_gate is not None:
        try:
            prompt_gate.verify_prompt(p, slide_id="page-01")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"prompt_gate.verify_prompt failed: {exc}")
    if len(p.strip()) < PROMPT_TARGET_MIN:
        fails.append(f"prompt length {len(p.strip())} below target {PROMPT_TARGET_MIN}")

    # 2) assembly + pypdf verify on a synthetic 2016x2688 background.
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        bg = td / "bg.png"
        Image.new("RGB", (2016, 2688), (242, 230, 215)).save(bg)
        m = {
            "client_name": "Test Client",
            "brand": brand,
            "page_count": 2,
            "pages": [
                {"id": "p1", "fields": [
                    {"name": "ClientName", "type": "text", "x": 1080, "y": 240, "w": 760, "h": 90, "flags": ""},
                    {"name": "Notes", "type": "textarea", "x": 220, "y": 1180, "w": 1576, "h": 420, "flags": "multiline"},
                ]},
                {"id": "p2", "fields": [
                    {"name": "Agree", "type": "checkbox", "x": 220, "y": 560, "w": 40, "h": 40, "flags": ""},
                    {"name": "Category", "type": "choice", "x": 220, "y": 760, "w": 400, "h": 60,
                     "flags": "", "options": ["Executive", "Coach"]},
                ]},
            ],
        }
        pdf = td / "wb.pdf"
        fc = assemble_workbook(m, [str(bg), str(bg)], pdf, brand)
        if fc != 4:
            fails.append(f"expected 4 fields, got {fc}")
        v = verify_pdf(pdf, 2, fc)
        if v["pages"] != 2:
            fails.append(f"expected 2 pages, got {v['pages']}")
        if v["fields"] != 4:
            fails.append(f"expected 4 fields read-back, got {v['fields']}")
        if not v["need_appearances"]:
            fails.append("NeedAppearances not read back as true")

    if fails:
        print("workbook_builder selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("workbook_builder selftest -> PASS "
          "(prompt band + rich gate + 2-page assembly + pypdf fields/NeedAppearances)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
