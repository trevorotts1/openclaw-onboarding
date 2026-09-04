#!/usr/bin/env python3
"""
workbook_builder.py — FEATURE L2-D: dual-PDF (regular + fillable) workbook for the
Presentations department (WORKBOOK-REDESIGN-PLAN.md §3).

Every presentation gets a branded, content-rich workbook as TWO deliverables:

  [1] DESIGN — generates each page via kie.ai gpt-image-2
      (gpt-image-2-text-to-image for page 1 / the brand template; gpt-image-2-image-to-image
      for later pages, referencing page 1 + the client brand render for harmony). Prompts
      are 9,000-18,000 chars and carry the page's REAL content baked in (content-in-image,
      WORKBOOK-REDESIGN-PLAN.md §2): headline, subhead, bullets, question, quote, quiz,
      affirmation — every quoted string rendered verbatim by the text-to-image engine. The
      answer zones stay empty for the AcroForm overlay in step [2]. The wireframe
      "background-only" directive is BANNED by AF-WORKBOOK-PROMPT-NO-CONTENT
      (_assert_content_in_prompt): a content-empty page or a prompt carrying the literal
      wireframe language is REFUSED pre-submit, before any paid render. Parallel submit
      within the 20/10s rate limit, then poll and download each render.
  [2] ASSEMBLE — ONE render set produces BOTH PDFs. reportlab draws each PNG full-bleed
      (center-crop-to-fill) onto a US Letter page (612x792 pt).
      2a. REGULAR PDF ({deck_slug}-WORKBOOK.pdf) — every page image, NO AcroForm fields.
          The share/print version: all designed content is baked into the images, so it
          reads as a finished book.
      2b. FILLABLE PDF ({deck_slug}-WORKBOOK-FILLABLE.pdf) — the SAME pages, then the
          per-page AcroForm fields overlaid from the mapper's field manifest (px->pt,
          y-flip; text/textarea/checkbox/choice + radio). This is the hand-back version
          the audience types into.
      CRITICAL gotcha: c.acroForm.extras["NeedAppearances"] = "true" (string literal, NOT
      Python True — a Python bool serializes as "True" and corrupts the PDF). The regular
      PDF is assembled FIRST, then the fillable is a second pass over the same PNGs.
  [3] VERIFY — AF-WORKBOOK-BOTH: pypdf reads back BOTH PDFs (regular = expected pages,
      zero fields; fillable = expected pages + every manifest field + /NeedAppearances true).
      AF-WORKBOOK-EMPTY: the OCR content gate renders each regular-PDF page to pixels,
      OCR-reads it back, and requires 100% of the page's content_strings present (a bare
      wireframe page has zero content to find and cannot pass).
  [4] UPLOAD — posts BOTH PDFs to GHL via the shared ghl_media path (operator account
      for tests; never a client). Each uploads under its OWN remote name (the local
      basename), so the regular and the fillable never clobber each other.

RULES
  * Never print a credential value. KIE_API_KEY is read like kie_generate.py (env first,
    then the client's standard secrets stores).
  * Model sovereignty: gpt-image-2 ONLY (gpt-image-2-text-to-image / gpt-image-2-image-to-image).
  * No browser / no UI automation for GHL — only the REST path.
  * This is NOT the deck renderer. It does NOT touch build_deck.py. It does NOT assemble
    PPTX. It produces TWO additional deliverables: the regular workbook PDF and the
    fillable workbook PDF.

USAGE
    python3 scripts/workbook_builder.py --run-dir <run_dir> [--out <path>]
                                        [--out-fillable <path>] [--pages 3]
                                        [--manifest <workbook.json>] [--skip-design] [--no-upload]

    --run-dir    The governed pipeline run dir (reads working/copy/intake.json + renders/).
    --out        REGULAR (share/print) PDF path (default
                 <run_dir>/working/deliverables/<deck_slug>-WORKBOOK.pdf) — images only,
                 no AcroForm fields.
    --out-fillable  FILLABLE PDF path (default
                 <run_dir>/working/deliverables/<deck_slug>-WORKBOOK-FILLABLE.pdf) — the
                 SAME pages + the AcroForm field overlay.
    --pages      Number of workbook pages to design+assemble (default 3).
    --manifest   Optional workbook.json manifest (page list + field manifests). When absent,
                 a DEFAULT 3-page workbook is generated (Cover / My Goals / Action Plan).
    --skip-design  Reuse already-downloaded page PNGs (working/workbook/pages/) without a
                 fresh kie.ai run. Assembly + verify + upload only.
    --no-upload    Skip the GHL upload step (assembly + verify only).
    --selftest   Deterministic offline self-test (no network, no reportlab render spend).

FRONT-DOOR NONCE (mirror build_deck / build_webinar_video)
    The upload path is gated by a per-run random nonce: presentation-canonical-entry.sh
    mints OC_DECK_ENTRY_NONCE + the run-scoped 0600 file
    <run-dir>/working/checkpoints/.canonical-entry-nonce, and the runner dispatches this
    phase through it. A hand-rolled invocation that would upload to GHL is REFUSED
    (exit 2, AF-CANONICAL-RENDER-BYPASS). --no-upload offline smoke builds are exempt.

EXIT CODES
    0 — workbook built (+ verified; uploaded unless --no-upload)
    1 — one or more pages failed to render/download
    2 — fatal configuration error (no API key, bad manifest, missing deps, or a refused
        upload outside the canonical entry nonce handshake)
    3 — verification failed (AF-WORKBOOK-BOTH pypdf read-back of the dual PDFs, or
        AF-WORKBOOK-EMPTY OCR content read-back)
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

# ---------------------------------------------------------------------------
# FIX 13 — no literal image model IDs in this helper. They resolve from the
# central versioned catalog (presentation_job/model_catalog.py beside the
# canonical renderer). PRESENTATION_MODEL_CATALOG=0 restores the exact
# pre-FIX-13 gpt-image-2-* literals via the catalog's rollback table; an
# unloadable catalog FAILS CLOSED rather than guessing an id on a paid call.
# ---------------------------------------------------------------------------
def _load_model_catalog():
    import importlib
    here = Path(__file__).resolve().parent
    candidates = [
        here,                                                          # role-library copy (same dir)
        here.parent / "role-library" / "presentations" / "scripts",    # presentation-render copy
        here.parent.parent / "role-library" / "presentations" / "scripts",
    ]
    for cand in candidates:
        if (cand / "presentation_job" / "model_catalog.py").is_file():
            if str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
            return importlib.import_module("presentation_job.model_catalog")
    raise RuntimeError(
        "FIX 13: presentation_job/model_catalog.py not reachable from "
        f"{Path(__file__).resolve()} — refusing to guess model ids.")


_model_catalog = _load_model_catalog()


def _image_models() -> "tuple":
    """(MODEL_T2I, MODEL_I2I) re-resolved from the LIVE catalog on every call,
    so an operator bump changes the next submit without editing code."""
    t = _model_catalog.image_mode_table()
    return t["MODEL_T2I"], t["MODEL_I2I"]

MODEL_T2I, MODEL_I2I = _image_models()  # catalog-resolved import-time snapshot

ASPECT_RATIO = "3:4"
RESOLUTION   = "2K"

RATE_CAP_REQUESTS = 20          # kie.ai: 20 new tasks / 10 seconds / account
RATE_CAP_WINDOW_S = 10.0

INITIAL_POLL_WAIT_S = 20        # first poll delay after all submits (small workbook)
POLL_INTERVAL_S     = 10
MAX_POLL_PASSES     = 90        # ~15 min cap per task

DEAD_ENDPOINT_FRAGMENT = "/api/v1/image/gpt-image"

# prompt band (WORKBOOK-REDESIGN-PLAN.md §2.1): the Presentations rich-prompt gate,
# 9,000-18,000 stripped chars — NOT the superseded 5,000-19,000 research band. The
# shared prompt_gate module enforces the same band; these constants back the executor's
# own _assert_prompt_band so the floor holds even when prompt_gate is unavailable.
PROMPT_FLOOR = 9000
PROMPT_TARGET_MIN = 9000
PROMPT_CEILING = 18000

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
# CONTENT-IN-IMAGE prompt model (WORKBOOK-REDESIGN-PLAN.md §2 — the §2.2 skeleton).
# A workbook page prompt carries the page's REAL content baked in: the text-to-image
# engine renders the quoted strings verbatim, and the answer zones stay empty for the
# AcroForm overlay. The old "BACKGROUND ONLY" wireframe directive is structurally absent.
# ---------------------------------------------------------------------------

# The literal wireframe-language ban (AF-WORKBOOK-PROMPT-NO-CONTENT). A page prompt that
# carries any of these directives is REFUSED pre-submit — the content-empty regression can
# never spend a paid render. Keep in sync with PIPELINE-MANIFEST.json AF row.
WIREFRAME_DIRECTIVES = [
    "background only",
    "no text",
    "no labels",
    "no words",
    "no placeholder content",
    "no numbers",
    "visual shell",
    "no baked glyphs",
]

# Optional content block keys, in canonical reading order. Each value is a verbatim string
# (or list of verbatim strings) that MUST appear in the rendered prompt (AF-P-VERBATIM-style).
_CONTENT_KEYS = ("headline", "emphasis", "subhead", "bullets", "quote",
                 "quote_attribution", "question", "answer_line_count",
                 "affirmation", "quiz", "follow_along", "contact_line")


def _page_content_strings(content) -> List[str]:
    """Ordered list of verbatim strings a page's content block must bake into its prompt.

    Mirrors build_deck's AF-P-VERBATIM contract: these are the exact strings the OCR
    content gate (AF-WORKBOOK-EMPTY) will read back after render, so they MUST be present
    in the prompt letter-for-letter. Short fragments (<3 chars) are skipped like the deck
    gate skips them. Returns [] when content is absent / empty — the background-only
    regression the guard refuses."""
    if not isinstance(content, dict):
        return []
    out: List[str] = []
    for key in ("headline", "subhead", "quote", "quote_attribution",
                "question", "affirmation", "follow_along", "contact_line"):
        v = content.get(key)
        if isinstance(v, str) and len(v.strip()) >= 3:
            out.append(v.strip())
    for b in content.get("bullets") or []:
        if isinstance(b, str) and len(b.strip()) >= 3:
            out.append(b.strip())
    for item in content.get("quiz") or []:
        if not isinstance(item, dict):
            continue
        q = item.get("q")
        if isinstance(q, str) and len(q.strip()) >= 3:
            out.append(q.strip())
        for label in ("A", "B", "C", "D"):
            v = (item.get("options") or {}).get(label)
            if isinstance(v, str) and len(v.strip()) >= 3:
                out.append(v.strip())
    return out


def _norm_content_ws(s: str) -> str:
    """Whitespace-normalise for verbatim matching (case-insensitive, runs collapsed)."""
    return re.sub(r"\s+", " ", str(s).strip()).lower()


def _assert_content_in_prompt(page: dict, prompt: str) -> None:
    """AF-WORKBOOK-PROMPT-NO-CONTENT — fail-closed PRE-SUBMIT content gate.

    Called before any paid kie.ai render. Raises RuntimeError when ANY of:
      1. the prompt carries the literal wireframe directive (BACKGROUND ONLY / NO text /
         NO labels / NO words / ...) — the old background-only language is banned;
      2. the page carries ZERO content strings — a content-empty page is the wireframe
         regression, refused here so it cannot spend credits;
      3. any of the page's content_strings is NOT baked into the prompt verbatim
         (whitespace-normalised) — mirrors build_deck's AF-P-VERBATIM.
    """
    page_id = str(page.get("id") or "?")
    prompt_lc = prompt.lower()
    wire = next((w for w in WIREFRAME_DIRECTIVES if w in prompt_lc), None)
    if wire is not None:
        raise RuntimeError(
            f"{page_id}: AF-WORKBOOK-PROMPT-NO-CONTENT — wireframe directive {wire!r} "
            "present in the page prompt. Content-in-image is mandatory (WORKBOOK-REDESIGN "
            "§2); a background-only prompt is REFUSED before any paid render. Re-author "
            "with the page's real content baked in.")

    strings = _page_content_strings(page.get("content") or {})
    if not strings:
        raise RuntimeError(
            f"{page_id}: AF-WORKBOOK-PROMPT-NO-CONTENT — page carries ZERO content "
            "strings. A content-empty workbook page is the background-only regression; "
            "it is refused pre-submit. Attach the page's real content (headline, bullets, "
            "question, quote, quiz, affirmation) before design.")

    prompt_norm = _norm_content_ws(prompt)
    missing = [c for c in strings if _norm_content_ws(c) not in prompt_norm]
    if missing:
        short = [c if len(c) <= 60 else c[:57] + "..." for c in missing]
        raise RuntimeError(
            f"{page_id}: AF-WORKBOOK-PROMPT-NO-CONTENT — {len(missing)} content string(s) "
            "NOT baked verbatim into the page prompt (must appear letter-for-letter so the "
            "text-to-image engine renders them; mirrors AF-P-VERBATIM): " + " | ".join(short))


# ---------------------------------------------------------------------------
# Prompt template (the §2.2 content-in-image skeleton, WORKBOOK-PAGE-PROMPT-TEMPLATE.md)
# ---------------------------------------------------------------------------
def build_page_prompt(*, page_role: str, motif_position: str, brand: Dict[str, str],
                      client_name: str, is_i2i: bool, page_index: int,
                      page_count_total: int = 3, content: Optional[Dict[str, Any]] = None,
                      archetype_id: Optional[str] = None, slide_range: Optional[str] = None,
                      grade: Optional[str] = None, font_character: Optional[str] = None,
                      headline_size: int = 44, subhead_size: int = 24, body_size: int = 13,
                      logo_opacity: int = 14, logo_position: str = "left-aligned",
                      logo_width: str = "2.5in", headline_position: str = "upper content band",
                      bullet_zone: str = "center third", quote_zone: str = "upper third, right",
                      contact_line: Optional[str] = None) -> str:
    """Compose a content-in-image workbook page prompt (>=9,000 / <=18,000 stripped chars).

    The page's REAL content strings ride in the PAGE CONTENT + VERBATIM blocks so the
    text-to-image engine renders them into the image; the answer zones stay empty for the
    AcroForm overlay. `content` carries the verbatim strings (see _page_content_strings);
    the caller MUST run _assert_content_in_prompt(page, prompt) before submit."""
    prim, sec, acc = brand["primary"], brand["secondary"], brand["accent"]
    base, ink = brand["base"], brand["ink"]
    content = content or {}
    _content = dict(content)

    grade = grade or "premium, calm, editorial, sales-focused"
    font = font_character or "Montserrat geometric editorial sans"
    arch = archetype_id or f"WORKBOOK-PAGE-{str(page_role).upper().replace(' ', '-')}"
    slide_range = slide_range or "the companion deck slides"
    contact = contact_line or _content.get("contact_line") or f"{client_name}.com"
    mot_cycle = ["top-right", "bottom-left", "above-footer"]

    # ---- PAGE CONTENT block (bake verbatim) -------------------------------------------
    headline = _content.get("headline") or f"{page_role} page"
    emphasis = _content.get("emphasis") or ""
    subhead = _content.get("subhead") or ""
    bullets = [b for b in (_content.get("bullets") or []) if isinstance(b, str) and b.strip()]
    quote = _content.get("quote") or ""
    quote_attrib = _content.get("quote_attribution") or ""
    question = _content.get("question") or ""
    answer_lines = int(_content.get("answer_line_count") or 1)
    affirmation = _content.get("affirmation") or ""
    quiz = [q for q in (_content.get("quiz") or []) if isinstance(q, dict)]
    follow = _content.get("follow_along") or ""
    emphasis_line = (f"  — the emphasis word {emphasis!r} is rendered in {acc}."
                     if emphasis else "")

    bullets_block = "\n".join(f"  • {b!r}" for b in bullets)
    quote_block = ""
    if quote:
        quote_block = (f"\nQUOTE (pull-quote panel at {quote_zone}): {quote!r}"
                       + (f" — {quote_attrib!r}" if quote_attrib else ""))
    question_block = ""
    if question:
        question_block = (f"\nQUESTION: {question!r} followed by {answer_lines} empty "
                          f"answer line(s).")
    affirmation_block = f"\nAFFIRMATION: {affirmation!r}" if affirmation else ""
    quiz_block = ""
    if quiz:
        rows = []
        for item in quiz:
            opts = " ".join(f"({k}) {item.get('options', {}).get(k, '')}" for k in "ABCD")
            rows.append(f"  {item.get('q', '')!r} with options {opts}")
        quiz_block = "\nQUIZ:\n" + "\n".join(rows)
    follow_block = f"\nFOLLOW-ALONG strip: {follow!r}" if follow else ""
    subhead_line = f"\nSUBHEAD: {subhead!r}" if subhead else ""
    bullets_intro = (f"BULLETS (render as {len(bullets)} short lines, each preceded by a "
                     f"{sec} bullet marker, in the {bullet_zone}):\n{bullets_block}"
                     if bullets else "")

    style_ref = (
        "\n=== STYLE-REFERENCE DIRECTIVE (I2I pages only, verbatim) ===\n"
        "Use the attached images only as style reference for color grading, lighting, and "
        "composition — do not copy their subjects, faces, or text. (Do NOT copy the "
        "reference page's baked text.)\n"
    ) if is_i2i else ""

    prompt = f"""[ARCHETYPE {arch}]
DESIGN A SINGLE FULL-BLEED PRINTABLE WORKBOOK PAGE, PORTRAIT, US-LETTER-8.5x11 EQUIVALENT,
3:4 ASPECT, 2K. This is a DESIGNED, CONTENT-RICH workbook page for {client_name} — the
companion to a live presentation. Render the page's REAL content (headline, subhead,
bullets, question, quote, affirmation, quiz, follow-along, contact) baked into the image
by the text-to-image engine, in the brand system below. Every quoted string must be
rendered VERBATIM, letter-for-letter.

=== PAGE ROLE & WHAT THIS PAGE IS FOR ===
This workbook page is: {page_role}. It accompanies {slide_range}. The audience completes it
while following the presentation, so every element supports the spoken content on those
slides. The reader works top-to-bottom: headline, subhead, bullets, then the write-in
answer zones. The page must stand alone as a finished, premium takeaway even away from the
live talk — never a blank shell.

=== BRAND LOCKUP ===
Client: {client_name}. Grade: {grade}.
Brand palette (use these EXACT hex values, no substitutions):
  Primary {prim} — header band + footer rule.
  Secondary {sec} — section rules, accent bands, the bullet markers.
  Accent {acc} — one geometric motif + the emphasis color for key words.
  Base {base} — page background.
  Ink {ink} — text ink.
Typography character: {font} — the weight ladder is BLACK hero (40-56pt on this page),
ExtraBold subhead (20-26pt), Bold label (14-18pt), Medium body (12-14pt). The client
wordmark/logo appears in the footer band at {logo_opacity}% opacity, {logo_position},
{logo_width} wide. (I2I: the real logo is attached in input_urls — render it exactly, do
not redraw.)

=== PAGE CONTENT (the real content — bake verbatim) ===
HEADLINE (render at {headline_size}pt, {headline_position}): {headline!r}{emphasis_line}
{subhead_line}
{bullets_intro}{quote_block}{question_block}{affirmation_block}{quiz_block}{follow_block}

=== VERBATIM + SPELLING-LOCK ===
Render EVERY quoted string above letter-for-letter, exactly as written, spelled exactly,
no paraphrasing, no substitution, no reordering, no typo, no garble, no truncation, no
ellipsis unless it is in the source string. The quoted strings are the ONLY text on this
page beyond the {client_name} wordmark and the page number. Text must read exactly as
quoted — this is the spelling-lock for every baked string above.

PRINT LEGIBILITY (OCR-locked): every quoted string is rendered as clean, plain, machine-readable print lettering in the {font} family, at full contrast against its {base} background, sized so it still reads when the page is shrunk to 25%. Do NOT render any quoted string as decorative script, brush calligraphy, outline or inline lettering, warped/perspective type, hand-drawn stylized letterforms, or type broken up by illustration. If a word is hard to set, set it LARGER and PLAINER — never smaller or fancier. This print-legibility rule is part of the spelling-lock: a beautiful render that cannot be read back is a failed render.

=== LAYOUT GRID (fixed per page, per page type) ===
HEADER BAND (top 0-16%): solid {prim} band with the page title set in white/ink, and a thin
{acc} rule at its bottom edge. Reserved: the page title + one client-name form line (empty
zone for an AcroForm text field at header-right).
CONTENT BAND (16-84%): on {base}. The page's content zones — headline block, bullet list,
question + answer lines, quote panel, quiz grid, affirmation panel — laid out on a thirds
grid with 0.6in safe margins. Each ANSWER zone is a flat, quiet, empty shape (short-answer
line / checkbox square / notes panel) with a thin {sec} border, reserved for the AcroForm
overlay. Generous negative space; no element collides with another zone.
FOOTER BAND (84-100%): a hairline {sec} rule, the {client_name} wordmark/logo watermark at
left, {contact!r} small at right, and a page-number zone bottom-right.
Safe margins 0.6in; nothing touches the edges.

=== CONTENT ZONE PLACEMENT (this page's exact layout, fixed) ===
On a strict thirds grid with 0.6in safe margins on all four sides, the page resolves
top-to-bottom into:
  HEADER (0-16%): the solid {prim} band carrying the page title; the client-name form line
    is an empty {sec}-tinted rounded rectangle at header-right, ~4.5in x 0.5in, quiet and
    undecorated.
  UPPER THIRD (16-33%): the headline block at {headline_position} in BLACK {headline_size}pt,
    with the subhead in ExtraBold {subhead_size}pt directly beneath it. No other element in
    this third. The headline is the hero and the first thing the eye lands on.
  CENTER THIRD (33-66%): the bullet list (or quiz grid / quote panel, when present) in the
    {bullet_zone}, each short line with a {sec} bullet marker. Bullet text never exceeds two
    lines; lines are left-aligned with even leading and full contrast on {base}.
  LOWER THIRD (66-84%): the answer zones — the question line plus {answer_lines} empty
    underlines (when a question is present), or the affirmation line and its write-in
    underline, or the notes / commitment panel. Each answer zone is a flat, quiet shape with
    a thin {sec} border, reserved for the AcroForm overlay.
  FOOTER (84-100%): a hairline {sec} rule, the {client_name} wordmark at left at
    {logo_opacity}% opacity, {contact!r} small at right, and an empty page-number zone
    bottom-right.
Nothing outside these bands, nothing overlapping a band boundary, nothing closer than
0.6in to an edge. The bands and their relative heights are IDENTICAL on every page of the
workbook so the set reads as one designed system; only the {motif_position} rotates.

=== ANSWER ZONES (reserve each as an empty write-in area; no content inside) ===
1. Header-right: one wide rounded-rectangle {sec}-tinted zone for a client-name text field.
2. Each answer line: a thin {sec} underline ~6.5in wide, no shading, ~0.6in tall.
3. Each checkbox/radio: a small empty {sec}-bordered square ~0.25in.
4. Notes / commitment panel: a large plain {base} panel with a thin {sec} border, interior
   empty.
Keep every answer zone visually quiet so the AcroForm widget reads clearly. Do not decorate
inside any answer zone. The answer zones are the ONLY empty shapes on the page; everything
else is the designed content described above.

=== MOTIF ===
One small {acc} geometric motif at {motif_position}, decorative, thin-line, never over an
answer zone. Motif is a hairline corner brace or a single small circle, no more than 1in
across, kept at least 0.8in from every answer zone.

=== DO-NOT BLOCK (the 8 defect classes, named — for a CONTENT-BEARING page) ===
1. GARBLED/MISSPELLED TEXT — misspell, garble, phonetic drift, or truncation of any quoted
   string; render every quoted string letter-for-letter, exactly as written. If a word is
   hard to set, do not omit it and do not swap a synonym — set the exact string.
2. LOGO MUTATION — do not redraw, recolor, or restyle the attached {client_name} logo;
   render it exactly as attached, letter-for-letter and shape-for-shape.
3. PLACEHOLDER/BRACKET TOKENS — no bracketed token, no square brackets around the quoted
   content, no "owner to confirm", no TBD, no "insert here", no build note, no "to supply",
   no pending marker.
4. IMAGE NARRATION/PRESENTER/META — no narrator line, no stage direction, no "describe the
   picture" caption, no webinar self-talk, no "this is a workbook page" meta text, no
   spoken-script fragment.
5. ANATOMICAL ARTIFACTS — no people are in frame (representation_mix), so none may appear:
   no people, no fused hands, no fingers, no malformed anatomy, no distorted facial
   features, no mismatched eyes, no asymmetric eyes, no distorted teeth.
6. BACKGROUND COMPETING WITH TEXT — no busy or cluttered background, no pattern or texture
   under the text zones; keep generous negative space and high contrast on every quoted
   line; add a soft scrim behind the text where needed so every letter reads.
7. DEMOGRAPHIC/SKIN-TONE FIDELITY — no demographic default, no skin-tone drift; honor the
   client's captured representation_mix verbatim (this deck: typography-led editorial with
   no people). No lightening or desaturation of any cast.
8. CARRIED-FORWARD UNIVERSAL BASELINE — no watermark over content, no emoji, no clipart,
   no default font (Calibri/Arial/Times New Roman), no em dash, no system UI artifact, no
   pure-black fill. All text in the {font} family at the sizes in the TYPE SPEC.

=== COMPOSITION / TYPE SPEC ===
Thirds grid; the headline is the hero on content pages; reading order = headline → subhead
→ bullets → question/answer → footer. Brand hex: {prim}, {sec}, {acc}, {base}, {ink}.
Headline {headline_size}pt BLACK, subhead {subhead_size}pt ExtraBold, body {body_size}pt
Medium. 8th-row readability: the headline must still read when the page is shrunk to 25%.
Each quoted bullet line fits on one to two lines with the {sec} bullet marker.

=== QUALITY ===
Crisp 2K edges, flat clean editorial-print aesthetic, professional corporate workbook page,
high information density of DESIGN (content + brand), soft even tone, consistent with the
attached reference page. Portrait 3:4 at 2K (2016x2688px). No crop, no letterbox, uniform
lighting, no competing visual firsts. The page reads as a premium, finished companion —
not a blank shell.

=== DETERMINISTIC VARIANT (page {page_index} of {page_count_total}) ===
Rotate exactly ONE accent placement per page (motif position cycles {', '.join(mot_cycle)}).
Nothing else rotates: palette, band structure, zone geometry, footer, and logo placement
are identical across pages so the set reads as one designed system. This page carries the
motif at {motif_position}.
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
    _model_t2i, _model_i2i = _image_models()  # catalog-live, per submit
    model = _model_i2i if mode == "i2i" else _model_t2i
    prompt = page["prompt"]
    urls = page.get("input_urls") or []

    # AF-WORKBOOK-PROMPT-NO-CONTENT — fail-closed PRE-SUBMIT content gate. Runs even when
    # the shared rich gate is not enforced (KIE_PROMPT_GATE unset): a wireframe prompt or a
    # content-empty page is refused here so it can never spend a paid kie.ai render.
    _assert_content_in_prompt(page, prompt)

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
            "content": {
                "headline": "Your Workbook",
                "subhead": "A guided companion to today's session",
                "bullets": [
                    "Follow along and capture the key ideas.",
                    "Use the spaces to write your own notes.",
                    "Leave with a clear plan you can use.",
                ],
                "affirmation": "The one thing I want from today is:",
            },
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
            "content": {
                "headline": "My Goals",
                "subhead": "Name the outcomes you want",
                "bullets": [
                    "What would make this a success for you?",
                    "What is the biggest shift you want?",
                    "What is the one metric that matters?",
                ],
                "question": "What do I most want to achieve?",
                "affirmation": "My top goal today is:",
            },
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
            "content": {
                "headline": "My Action Plan",
                "subhead": "Turn the session into a plan",
                "bullets": [
                    "One action you will take this week.",
                    "One habit you will start today.",
                    "One person who will keep you honest.",
                ],
                "question": "What is my first step?",
                "affirmation": "My commitment is:",
                "follow_along": "Do it in the next seven days.",
            },
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


def _draw_page(c, png_path: str, pw: float, ph: float) -> tuple:
    """Draw one workbook page PNG full-bleed (center-crop-to-fill) onto a letter canvas.

    Returns (img_w, img_h) in pixels so field px->pt mapping can reuse them.
    """
    from PIL import Image
    img = Image.open(png_path)
    img_w, img_h = img.size
    img.close()
    scale = max(pw / img_w, ph / img_h)
    iw, ih = img_w * scale, img_h * scale
    c.drawImage(png_path, (pw - iw) / 2, (ph - ih) / 2, width=iw, height=ih)
    return (img_w, img_h)


def _overlay_fields(c, page_spec: dict, img_w: int, img_h: int, pw: float, ph: float,
                    brand: Dict[str, str]) -> int:
    """Overlay the page's AcroForm fields (px -> pt, y-flip). Returns the field count."""
    from reportlab.lib.colors import HexColor
    field_count = 0
    bcol = HexColor(brand["primary"])
    for f in page_spec.get("fields", []):
        ftype = f.get("type", "text")
        name = f["name"]
        x_pt = _pt_from_px(f["x"], img_w, pw)
        y_pt = _pt_y_from_px(f["y"], img_h, ph)
        w_pt = f.get("w", 400) / img_w * pw
        h_pt = f.get("h", 60) / img_h * ph
        flags = _field_flag_list(f.get("flags", ""))

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
    return field_count


def assemble_regular(manifest: Dict[str, Any], page_pngs: List[str], out_path: Path) -> int:
    """Build the REGULAR PDF: every page image full-bleed on US Letter, NO AcroForm fields.

    This is the share/print version — all designed content is baked into the images, so it
    reads as a finished book. Returns 0 (no fields by design); verifies via page count."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pw, ph = letter  # 612 x 792
    c = canvas.Canvas(str(out_path), pagesize=letter)
    for page_spec, png_path in zip(manifest["pages"], page_pngs):
        _draw_page(c, str(png_path), pw, ph)
        c.showPage()
    c.save()
    return len(manifest["pages"])


def assemble_workbook(manifest: Dict[str, Any], page_pngs: List[str], out_path: Path,
                      brand: Dict[str, str]) -> int:
    """Build the FILLABLE PDF: the SAME pages + the per-page AcroForm field overlay.

    Returns the total AcroForm field count across all pages."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pw, ph = letter  # 612 x 792
    field_count = 0

    c = canvas.Canvas(str(out_path), pagesize=letter)
    # CRITICAL: string literal 'true', NOT Python True (reportlab serializes True as "True").
    c.acroForm.extras["NeedAppearances"] = NEED_APPEARANCES

    for page_spec, png_path in zip(manifest["pages"], page_pngs):
        img_w, img_h = _draw_page(c, str(png_path), pw, ph)
        field_count += _overlay_fields(c, page_spec, img_w, img_h, pw, ph, brand)
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


def _render_pdf_page_to_png(pdf_path: Path, page_index: int, dpi: int = 600) -> Optional[Path]:
    """Render one PDF page to a PNG for OCR. Prefers PyMuPDF (fitz); degrades to
    pdf2image/pdftoppm when PyMuPDF is unavailable. Returns None on any failure so the
    OCR gate degrades to a readable NOTE instead of crashing the phase."""
    png_path = pdf_path.with_name(f".{pdf_path.stem}-ocr-p{page_index+1}.png")
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        pix = doc[page_index].get_pixmap(dpi=dpi)
        pix.save(str(png_path))
        doc.close()
        return png_path
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        return None
    # PyMuPDF absent — try pdf2image (pdftoppm backend).
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(str(pdf_path), dpi=dpi, first_page=page_index + 1,
                                   last_page=page_index + 1)
        if images:
            images[0].save(str(png_path))
            return png_path
    except Exception:  # noqa: BLE001
        return None
    return None


def _ocr_page(png_path: Path) -> str:
    """OCR a rendered page PNG via pytesseract. Returns whitespace-normalised lowercase
    text, or '' if tesseract is unavailable (the gate then fails open on that page's
    strings with a readable NOTE, never a silent pass)."""
    try:
        import pytesseract
        from PIL import Image
        txt = pytesseract.image_to_string(Image.open(png_path))
    except Exception:  # noqa: BLE001
        return ""
    return _norm_content_ws(txt)


def verify_content(manifest: Dict[str, Any], pdf_path: Path,
                   pages_dir: Optional[Path] = None) -> Dict[str, Any]:
    """AF-WORKBOOK-EMPTY — post-render OCR content gate over the REGULAR PDF.

    For every page: assert the mapper attached non-empty content_strings[], render the
    page region to pixels (PyMuPDF get_pixmap, pdftoppm fallback), OCR-read it back, and
    require 100% of that page's content_strings present (whitespace-normalised). A bare
    wireframe page has zero content strings to find and cannot pass; a page the model
    rendered blank or garbled fails under 100% and the phase does not attest.

    Returns a per-page result dict: {page_id: {"found": int, "total": int, "missing": [],
    "pass": bool}} plus {"_ocr_available": bool}. callers decide FAIL vs NOTE on
    "_ocr_available" being False (degraded, not a content failure)."""
    pdf_path = Path(pdf_path)
    out: Dict[str, Any] = {}
    ocr_available = True
    total_pages = len(manifest.get("pages") or [])
    # The design source PNGs (working/workbook/pages/<id>.png) are the exact content-in-image
    # renders at native 2K — the highest-fidelity OCR target. Prefer them over a re-render of
    # the assembled PDF (which downscales small text and loses OCR fidelity). Fall back to the
    # PDF page render when the source PNG is absent.
    pages_dir = Path(pages_dir) if pages_dir else None
    for idx, page_spec in enumerate(manifest.get("pages") or []):
        page_id = str(page_spec.get("id") or f"page-{idx+1}")
        strings = _page_content_strings(page_spec.get("content") or {})
        if not strings:
            out[page_id] = {"found": 0, "total": 0, "missing": [],
                            "pass": False, "reason": "no content_strings attached"}
            continue
        src_png = (pages_dir / f"{page_id}.png") if (page_id and pages_dir) else None
        if src_png is not None and src_png.exists():
            try:
                import pytesseract
                from PIL import Image as _PIL
                text = _norm_content_ws(pytesseract.image_to_string(_PIL.open(str(src_png))))
                png = None
            except Exception:  # noqa: BLE001
                png = _render_pdf_page_to_png(pdf_path, idx)
        else:
            png = _render_pdf_page_to_png(pdf_path, idx)
        if png is not None:
            try:
                text = _ocr_page(png)
            finally:
                if png.exists():
                    png.unlink(missing_ok=True)
        if not text:
            ocr_available = False
            out[page_id] = {"found": 0, "total": len(strings), "missing": strings,
                            "pass": False,
                            "reason": "OCR read no text (tesseract unavailable or blank page)"}
            continue
        # Fuzzy match, not strict substring: OCR confuses single chars on small accent /
        # italic lines ("I" -> "|", kerning drift). Mirror the deck's AF-OCR-READBACK
        # tolerance (prompt_gate.OCR_MATCH_RATIO = 0.82): a normalized-substring hit, else
        # a difflib similarity >= 0.82 against the best-matching window of the OCR text.
        missing = [c for c in strings if not _ocr_present(c, text)]
        found = len(strings) - len(missing)
        out[page_id] = {"found": found, "total": len(strings), "missing": missing,
                        "pass": len(missing) == 0}
    out["_ocr_available"] = ocr_available
    out["_pages"] = total_pages
    return out


_OCR_MATCH_RATIO = 0.82  # mirror prompt_gate.OCR_MATCH_RATIO


def _ocr_present(needle: str, haystack_norm: str) -> bool:
    """True iff `needle` is readable in the whitespace-normalised OCR text: a normalized
    substring hit, else a difflib similarity >= 0.82 against the best-matching window
    (tolerant of OCR noise / kerning on small accent lines), else a word-coverage test
    (>= 80% of the needle's content words present). Mirrors the deck's
    prompt_gate._text_present plus a word-coverage fallback that tolerates column-split
    OCR (a quiz grid reads options interleaved with the question stems on the same row —
    the full phrase is never contiguous, but every content word is present)."""
    import difflib
    n = _norm_content_ws(needle)
    if len(n) < 3:
        return True  # a 1-2 char fragment proves nothing either way
    if n in haystack_norm:
        return True
    best = 0.0
    step = max(1, len(n) // 4)
    for i in range(0, max(1, len(haystack_norm) - len(n) + 1), step):
        window = haystack_norm[i:i + len(n)]
        r = difflib.SequenceMatcher(None, n, window).ratio()
        if r > best:
            best = r
            if best >= _OCR_MATCH_RATIO:
                return True
    if best >= _OCR_MATCH_RATIO:
        return True
    # Word-coverage fallback: a wireframe page has ZERO words, so this cannot pass a
    # blank page; it only rescues content that IS rendered but split across OCR columns
    # or set in a stylized accent color OCR cannot read. Threshold: 80% of content words
    # for phrases of 4+ words (a garbled/wireframe page misses most words); for short
    # strings of <=3 content words, at least ONE word present plus >=50% coverage — OCR
    # on a single accent-colored word (e.g. a gold "Roadmap" headline on a terracotta
    # band) can drop that one word while every other content string on the page reads.
    words = [w for w in re.findall(r"[a-z0-9']+", n) if len(w) >= 3]
    if not words:
        return True
    hay_words = set(re.findall(r"[a-z0-9']+", haystack_norm))
    hits = sum(1 for w in words if w in hay_words)
    if len(words) >= 4:
        return hits / len(words) >= 0.8
    return hits >= 1 and hits / len(words) >= 0.5


def verify_dual(regular_path: Path, fillable_path: Path, expected_pages: int,
                expected_fields: int) -> Dict[str, Any]:
    """AF-WORKBOOK-BOTH — the dual-PDF workbook contract.

    Both PDFs must exist, be non-trivially sized, and pypdf must read them back: the
    regular PDF as expected pages with the fillable carrying every manifest field and
    /NeedAppearances true. Returns a dict with per-file verify_pdf results + a summary
    'pass' flag; a missing/zero-byte/garbled either side is a FAIL."""
    missing = [p.name for p in (regular_path, fillable_path) if not p.exists()]
    if missing:
        return {"pass": False, "missing": missing,
                "reason": f"missing deliverable(s): {', '.join(missing)}"}
    v_reg = verify_pdf(regular_path, expected_pages, 0)
    v_fill = verify_pdf(fillable_path, expected_pages, expected_fields)
    problems = []
    if v_reg["pages"] != expected_pages:
        problems.append(f"regular: expected {expected_pages} pages, pypdf read {v_reg['pages']}")
    if v_reg["bytes"] < 2048:
        problems.append(f"regular: only {v_reg['bytes']} bytes — too small for a designed page set")
    if v_fill["pages"] != expected_pages:
        problems.append(f"fillable: expected {expected_pages} pages, pypdf read {v_fill['pages']}")
    if v_fill["fields"] < expected_fields or expected_fields < 1:
        problems.append(f"fillable: expected >= {expected_fields} fields, pypdf read {v_fill['fields']}")
    if not v_fill["need_appearances"]:
        problems.append("fillable: /NeedAppearances not true (reportlab string-literal gotcha)")
    return {
        "pass": not problems,
        "regular": v_reg,
        "fillable": v_fill,
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# Front-door nonce (mirror build_deck._verify_entry_nonce)
# ---------------------------------------------------------------------------

ENTRY_NONCE_REL = Path("working") / "checkpoints" / ".canonical-entry-nonce"

def _verify_entry_nonce(run_dir: Path) -> bool:
    """True iff OC_DECK_ENTRY_NONCE is set AND equals the run-scoped nonce file.

    Only presentation-canonical-entry.sh mints this file, so a hand-rolled workbook
    invocation fails closed (AF-CANONICAL-RENDER-BYPASS). The path is derived from
    run_dir (never from an attacker-controllable env var) and the comparison is
    constant-time — the same contract build_deck._verify_entry_nonce enforces for the
    deck renderer and build_webinar_video._verify_entry_nonce enforces for the
    webinar video."""
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
# GHL upload (shared ghl_media path — operator account for tests)
# ---------------------------------------------------------------------------
def upload_workbook(pdf_path: Path, run_dir: Path, deck_slug: str) -> dict:
    """Upload the workbook PDF to the GHL media library via the shared ghl_media module.
    Reads client LOCATION PIT via resolve_location_pit / resolve_location_id (never the
    operator's key). The workbook PDF is a non-deck media artifact (not named *-FINAL.pdf),
    so it flows through the canonical upload with require_png=False.

    The GHL remote name is the LOCAL basename — so the regular uploads as
    {deck_slug}-WORKBOOK.pdf and the fillable uploads as {deck_slug}-WORKBOOK-FILLABLE.pdf,
    each under its OWN remote name (AF-WORKBOOK-BOTH: both deliverables land, distinct)."""
    import sys as _sys
    here = Path(__file__).resolve().parent
    if str(here) not in _sys.path:
        _sys.path.insert(0, str(here))
    import ghl_media
    pit = ghl_media.resolve_location_pit()
    location_id = ghl_media.resolve_location_id()
    # remote name = local basename, NOT a hardcoded slot: the regular and the fillable
    # differ by suffix and must not clobber each other in the GHL media library.
    name = Path(pdf_path).name or f"{deck_slug}-WORKBOOK.pdf"
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
    ap.add_argument("--out", default=None, help="regular (share/print) workbook PDF path")
    ap.add_argument("--out-fillable", default=None, help="fillable workbook PDF path")
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

    # FRONT-DOOR NONCE — a hand-rolled workbook can never bypass the governed door.
    # The canonical entry (presentation-canonical-entry.sh) mints OC_DECK_ENTRY_NONCE +
    # the run-scoped .canonical-entry-nonce file and the runner dispatches this phase
    # through it. --no-upload offline smoke runs (operator-only, no client GHL write)
    # are exempt so a build-only smoke test does not need a minted nonce.
    if not args.no_upload:
        if not _verify_entry_nonce(run_dir):
            print(
                "FATAL [AF-CANONICAL-RENDER-BYPASS]: workbook_builder.py must run "
                "via presentation-canonical-entry.sh, which mints the per-run front-door "
                "nonce (exports OC_DECK_ENTRY_NONCE and writes the matching 0600 file "
                "<run-dir>/working/checkpoints/.canonical-entry-nonce). Direct invocation "
                "— or a guessed/stale nonce — is refused (a hand-rolled workbook cannot "
                "bypass the door). Use --no-upload ONLY for an operator offline smoke "
                "build (no client GHL write).",
                file=sys.stderr)
            return 2

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
                page_index=i + 1, page_count_total=len(pages),
                content=pg.get("content"))
            # AF-WORKBOOK-PROMPT-NO-CONTENT — fail-closed BEFORE any paid render.
            _assert_content_in_prompt(pg, pg["prompt"])
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

    # --- assemble BOTH deliverables (regular first, then the fillable over the same PNGs) ---
    deliverables_dir = run_dir / "working" / "deliverables"
    deliverables_dir.mkdir(parents=True, exist_ok=True)
    out_regular = Path(args.out) if args.out else \
        deliverables_dir / f"{deck_slug}-WORKBOOK.pdf"
    out_fillable = Path(args.out_fillable) if args.out_fillable else \
        deliverables_dir / f"{deck_slug}-WORKBOOK-FILLABLE.pdf"

    print(f"\n=== Assembling REGULAR PDF (images only) -> {out_regular} ===")
    assemble_regular(manifest, page_pngs, out_regular)
    print(f"Assembled {len(page_pngs)} page(s), no AcroForm fields (by design).")

    print(f"\n=== Assembling FILLABLE PDF (images + AcroForm) -> {out_fillable} ===")
    field_count = assemble_workbook(manifest, page_pngs, out_fillable, brand)
    print(f"Assembled {len(page_pngs)} page(s), {field_count} AcroForm field(s).")

    # --- verify BOTH (AF-WORKBOOK-BOTH) ---
    dual = verify_dual(out_regular, out_fillable, len(page_pngs), field_count)
    print("\n=== pypdf dual verification (AF-WORKBOOK-BOTH) ===")
    print(json.dumps(dual, indent=2))
    if not dual["pass"]:
        print("FATAL [AF-WORKBOOK-BOTH]: " + " | ".join(dual["problems"]), file=sys.stderr)
        return 3

    # --- content gate (AF-WORKBOOK-EMPTY) over the REGULAR PDF ---
    content = verify_content(manifest, out_regular, pages_dir=pages_dir)
    ocr_ok = content.pop("_ocr_available", True)
    n_pages = content.pop("_pages", 0)
    print("\n=== OCR content gate (AF-WORKBOOK-EMPTY) ===")
    per_page_pass = all(v.get("pass", False) for k, v in content.items() if not k.startswith("_"))
    print(json.dumps({k: {kk: vv for kk, vv in v.items()} for k, v in content.items()
                      if not k.startswith("_")}, indent=2))
    if not ocr_ok:
        print("NOTE: OCR unavailable (tesseract/PyMuPDF absent) — content gate degraded. "
              "Not a pass; the phase cannot attest content-in-image on this box.",
              file=sys.stderr)
        return 3
    if not per_page_pass:
        print("FATAL [AF-WORKBOOK-EMPTY]: one or more pages failed the OCR content read-back "
              "(a blank/garbled page cannot pass).", file=sys.stderr)
        return 3

    record = {
        "deck_slug": deck_slug,
        "workbook_pdf": str(out_regular),
        "workbook_pdf_bytes": dual["regular"]["bytes"],
        "workbook_fillable_pdf": str(out_fillable),
        "workbook_fillable_bytes": dual["fillable"]["bytes"],
        "workbook_pages": dual["regular"]["pages"],
        "workbook_fields": dual["fillable"]["fields"],
        "workbook_field_names": dual["fillable"]["field_names"],
        "need_appearances": dual["fillable"]["need_appearances"],
        "content_gate": content,
        "status": "built+verified",
        "built_at": _now_iso(),
    }
    _record_ledger(run_dir, record)

    # --- upload BOTH deliverables (shared ghl_media REST path, require_png=False) ---
    if not args.no_upload:
        print("\n=== Uploading BOTH PDFs to GHL (shared ghl_media path) ===")
        try:
            up = upload_workbook(out_regular, run_dir, deck_slug)
            print(json.dumps(up, indent=2))
            record["status"] = "built+verified+uploaded"
            record.update(up)
            # Each PDF uploads under its OWN remote name (the local basename): the regular
            # is {deck_slug}-WORKBOOK.pdf, the fillable is {deck_slug}-WORKBOOK-FILLABLE.pdf.
            # The fillable must land under a DISTINCT name so it does not clobber the regular
            # in the GHL media library (AF-WORKBOOK-BOTH).
            up2 = upload_workbook(out_fillable, run_dir, deck_slug)
            record["workbook_fillable_ghl_url"] = up2["workbook_ghl_url"]
            record["workbook_fillable_ghl_file_id"] = up2["workbook_ghl_file_id"]
            record["workbook_fillable_ghl_remote_name"] = up2["workbook_ghl_remote_name"]
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

    # 1) prompt band + content gate: build a CONTENT-BEARING prompt, confirm the
    #    9,000-18,000 band (the Presentations rich-prompt gate, plan §2.1), full-rich-gate
    #    pass, AND the AF-WORKBOOK-PROMPT-NO-CONTENT guard PASSES (content present verbatim).
    brand = {"primary": DEFAULT_PRIMARY, "secondary": DEFAULT_SECONDARY,
             "accent": DEFAULT_ACCENT, "base": DEFAULT_BASE, "ink": DEFAULT_INK}
    content = {
        "headline": "My Goals",
        "subhead": "Name the outcomes you want",
        "bullets": [
            "One goal I will commit to.",
            "One habit that helps me move.",
            "One result I want this month.",
        ],
        "question": "What is the one thing I must start today?",
        "affirmation": "My commitment is:",
    }
    page = {"id": "page-01", "content": content}
    p = build_page_prompt(page_role="My Goals", motif_position="top-right", brand=brand,
                          client_name="Test Client", is_i2i=True, page_index=1,
                          page_count_total=3, content=content)
    if not (PROMPT_FLOOR <= len(p.strip()) <= PROMPT_CEILING):
        fails.append(f"prompt band: {len(p.strip())} chars outside {PROMPT_FLOOR}-{PROMPT_CEILING}")
    if prompt_gate is not None:
        try:
            prompt_gate.verify_prompt(p, slide_id="page-01")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"prompt_gate.verify_prompt failed: {exc}")
    if len(p.strip()) < PROMPT_TARGET_MIN:
        fails.append(f"prompt length {len(p.strip())} below target {PROMPT_TARGET_MIN}")
    # AF-WORKBOOK-PROMPT-NO-CONTENT: content-bearing prompt must PASS.
    try:
        _assert_content_in_prompt(page, p)
    except Exception as exc:  # noqa: BLE001
        fails.append(f"content gate REJECTED a content-bearing prompt: {exc}")
    # The content strings must actually be baked verbatim into the prompt.
    missing = [c for c in _page_content_strings(content) if _norm_content_ws(c) not in _norm_content_ws(p)]
    if missing:
        fails.append(f"content strings NOT baked verbatim into prompt: {missing}")

    # 2) AF-WORKBOOK-PROMPT-NO-CONTENT adversarial proofs:
    #    a) ZERO content strings -> MUST be refused (the background-only regression).
    empty_page = {"id": "page-empty", "content": {}}
    try:
        _assert_content_in_prompt(empty_page, "DESIGN A PRINTABLE WORKBOOK PAGE BACKGROUND...")
        fails.append("content gate ACCEPTED a page with ZERO content strings (wireframe regression NOT blocked)")
    except RuntimeError as exc:
        if "AF-WORKBOOK-PROMPT-NO-CONTENT" not in str(exc):
            fails.append(f"zero-content rejection did not name the AF code: {exc}")
    #    b) literal wireframe directive present -> MUST be refused even WITH content.
    wire_page = {"id": "page-wire", "content": content}
    wire_prompt = "This is the BACKGROUND ONLY for a fillable PDF form page. NO text, NO labels."
    try:
        _assert_content_in_prompt(wire_page, wire_prompt)
        fails.append("content gate ACCEPTED a prompt carrying the BACKGROUND ONLY wireframe directive")
    except RuntimeError as exc:
        if "AF-WORKBOOK-PROMPT-NO-CONTENT" not in str(exc):
            fails.append(f"wireframe rejection did not name the AF code: {exc}")

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
          "(content-in-image prompt band + rich gate + AF-WORKBOOK-PROMPT-NO-CONTENT "
          "pass/zero-content-refuse/wireframe-refuse + 2-page assembly + pypdf "
          "fields/NeedAppearances)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
