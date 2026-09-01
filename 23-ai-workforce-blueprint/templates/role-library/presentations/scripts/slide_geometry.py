#!/usr/bin/env python3
"""slide_geometry.py — DETERMINISTIC pixel-level slide checks over BAKED renders.

The three checks the department promised and never had: does the text FIT, is it
SPELLED right, is it BIG enough to read. All three read the rendered PNGs — not the
prompts, not the copy file — because a baked image is what the audience sees.

WHY A SEPARATE MODULE: build_deck.py is already 506,921 bytes. These checks need OCR
word geometry (pytesseract.image_to_data), which nothing else in the pipeline uses.
build_deck.py keeps only three thin _chk_ wrappers so the manifest's py_symbol
lockstep (sync_check A3/B1) resolves against build_deck.py as it does for every other
autofail.

ZERO NEW DEPENDENCIES. pytesseract + PIL are the SAME pair prompt_gate._ocr_engine_available
already requires. No spell-checker library is installed on this fleet (measured:
pyspellchecker / enchant / hunspell / symspellpy / language_tool_python / wordfreq all
absent on both interpreters), so spelling is checked against the APPROVED COPY plus an
optional per-client proper-noun allowlist plus an optional system word list.

EVERY PIXEL THRESHOLD IS DERIVED FROM THE ACTUAL IMAGE, NEVER HARD-CODED. The render
resolution today is 2K (build_deck.py:218), and its numeric dimensions appear only
inside an error message (prompt_gate.py:505). Binding a threshold to a literal image
size would bind it to prose.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

# ── Thresholds ───────────────────────────────────────────────────────────────
# Reference height for the min_body_pt token. check_font_floor DEFINES the token as
# "pt-equiv @1080" (build_deck.py:5170) and repeats it in its own error text (:5218).
# A 1080px-tall 16:9 frame is the 540-point slide, so 1 pt-equiv = 2 px at the
# reference height. Everything scales from the real PNG height.
PT_REFERENCE_HEIGHT_PX = 1080.0
PT_PER_REFERENCE_PIXEL = 2.0        # px per pt-equiv AT the reference height

# A glyph box whose edge sits within this fraction of the slide's own dimension is
# treated as running off the slide. v3 G2: "no glyph bounding box within 2% of any
# slide edge". Applied PER AXIS against the real width/height.
TEXT_EDGE_MARGIN_FRAC = 0.02

# OCR noise floor. Below this confidence, or shorter than this, a token is not
# evidence of anything and is dropped before any measurement.
OCR_MIN_CONFIDENCE = 60.0
OCR_MIN_TOKEN_LEN = 3

# Two word boxes overlapping by more than this fraction of the SMALLER box's area are
# colliding text, not kerning slop.
TEXT_OVERLAP_AREA_FRAC = 0.10

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
_NON_ALNUM = re.compile(r"[^0-9a-z]+")
SYSTEM_WORDLIST_CANDIDATES = ("/usr/share/dict/words", "/usr/share/dict/web2")


def ocr_engine():
    """(pytesseract, PIL.Image) or (None, None). Byte-for-byte the same predicate as
    prompt_gate._ocr_engine_available (prompt_gate.py:514-526) — importable bindings AND a
    reachable tesseract binary. Duplicated rather than imported so this module has no
    import-order dependency on prompt_gate."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore  # noqa: F811
    except Exception:  # noqa: BLE001 — engine absent is an EXPECTED, recorded state
        return None, None
    try:
        pytesseract.get_tesseract_version()
    except Exception:  # noqa: BLE001 — python binding present but no tesseract binary
        return None, None
    return pytesseract, Image


def px_per_pt(image_height_px: int, reference_height_px: float = PT_REFERENCE_HEIGHT_PX) -> float:
    """Pixels per pt-equivalent for a render of this height.

        px_per_pt = PT_PER_REFERENCE_PIXEL * image_height_px / reference_height_px

    At the canonical 2K render height (reference_height_px == PT_REFERENCE_HEIGHT_PX)
    this is 2.1333…, so an 18-pt floor is 38.4 px. Derived from the PNG, never from
    RESOLUTION or from any literal image size. `reference_height_px` defaults to this
    module's own PT_REFERENCE_HEIGHT_PX but check_type_size's build_deck.py wrapper
    passes build_deck.SLIDE_GEOMETRY_PT_REFERENCE_HEIGHT_PX explicitly so the two
    modules' reference height can never silently diverge."""
    return PT_PER_REFERENCE_PIXEL * image_height_px / reference_height_px


def word_boxes(png_path) -> list:
    """[{'text','conf','left','top','width','height','line_num'}] for level-5 (word) rows whose
    confidence >= OCR_MIN_CONFIDENCE and whose stripped text is at least
    OCR_MIN_TOKEN_LEN characters. [] when the engine is absent or the image is
    unreadable — the CALLER decides policy, exactly as ocr_readback does.

    Uses pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT). Both the
    function and the Output enum were confirmed present on this fleet's OCR interpreter."""
    tesseract, PIL_Image = ocr_engine()
    if tesseract is None or PIL_Image is None:
        return []
    try:
        im = PIL_Image.open(str(png_path))
    except Exception:  # noqa: BLE001
        return []
    try:
        data = tesseract.image_to_data(im, output_type=tesseract.Output.DICT)
    except Exception:  # noqa: BLE001
        return []
    boxes = []
    n = len(data.get("level", []))
    for i in range(n):
        if data["level"][i] != 5:
            continue
        conf_val = data["conf"][i]
        if isinstance(conf_val, str):
            try:
                conf_val = float(conf_val)
            except (ValueError, TypeError):
                continue
        if conf_val < OCR_MIN_CONFIDENCE:
            continue
        text = (data["text"][i] or "").strip()
        if len(text) < OCR_MIN_TOKEN_LEN:
            continue
        boxes.append({
            "text": text,
            "conf": conf_val,
            "left": data["left"][i],
            "top": data["top"][i],
            "width": data["width"][i],
            "height": data["height"][i],
            "line_num": data.get("line_num", [0])[i],
        })
    return boxes


# ── Helper: boxes_overlap ────────────────────────────────────────────────────

def _boxes_overlap(a: dict, b: dict, image_w: int, image_h: int) -> bool:
    """True if a and b overlap by more than TEXT_OVERLAP_AREA_FRAC of the smaller box."""
    ax1, ay1 = a["left"], a["top"]
    ax2, ay2 = ax1 + a["width"], ay1 + a["height"]
    bx1, by1 = b["left"], b["top"]
    bx2, by2 = bx1 + b["width"], by1 + b["height"]
    ox1 = max(ax1, bx1)
    oy1 = max(ay1, by1)
    ox2 = min(ax2, bx2)
    oy2 = min(ay2, by2)
    if ox1 >= ox2 or oy1 >= oy2:
        return False
    overlap_area = (ox2 - ox1) * (oy2 - oy1)
    min_area = min(a["width"] * a["height"], b["width"] * b["height"])
    if min_area <= 0:
        return False
    return overlap_area > TEXT_OVERLAP_AREA_FRAC * min_area


# ── Provenance ────────────────────────────────────────────────────────────────

def _write_provenance(run_dir: Path, payload: dict) -> None:
    """Write working/qc/slide_geometry.json (best-effort, never raises). Records
    engine availability, per-slide image dimensions, the derived px_per_pt, the derived
    thresholds and every finding — so a deferred run is VISIBLE rather than silent.
    Mirrors _record_ocr_readback (build_deck.py:1289-1297) and the AF-IMAGE-QC-VISION
    provenance pattern."""
    try:
        qc_dir = run_dir / "working" / "qc"
        qc_dir.mkdir(parents=True, exist_ok=True)
        prov_path = qc_dir / "slide_geometry.json"
        _tess, _pil = ocr_engine()
        payload["engine_available"] = _tess is not None
        prov_path.write_text(json.dumps(payload, indent=2, default=str))
    except Exception:  # noqa: BLE001
        pass


# ── Helpers for loading run-dir data ──────────────────────────────────────────

def _read_json(path: Path) -> Optional[dict]:
    """Read and parse a JSON file; return None on any failure."""
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def _load_slides_copy(run_dir: Path, slides_path: Optional[Path] = None) -> list:
    """Load slides.json copy array. Falls back to run_dir/working/copy/slides.json."""
    if slides_path is not None and slides_path.exists():
        return _read_json(slides_path) or []
    sp = run_dir / "working" / "copy" / "slides.json"
    if sp.exists():
        return _read_json(sp) or []
    return []


def _load_intake(run_dir: Path) -> dict:
    """Load intake.json dict. Tries multiple fallback paths."""
    for rel in ("working/copy/intake.json", "intake.json", "working/intake.json"):
        p = run_dir / rel
        if p.exists():
            obj = _read_json(p)
            if isinstance(obj, dict):
                return obj
    return {}


def _get_allowlist(intake_obj: dict) -> set:
    """Collect proper-noun allowlist from intake.json fields."""
    allow = set()
    for key in ("proper_nouns",):
        val = intake_obj.get(key)
        if isinstance(val, list):
            for v in val:
                if isinstance(v, str) and v.strip():
                    allow.add(v.strip())
    brand = intake_obj.get("brand")
    if isinstance(brand, dict):
        for key in ("proper_nouns", "name"):
            val = brand.get(key)
            if isinstance(val, list):
                for v in val:
                    if isinstance(v, str) and v.strip():
                        allow.add(v.strip())
            elif isinstance(val, str) and val.strip():
                allow.add(val.strip())
    client_name = intake_obj.get("client_name")
    if isinstance(client_name, str) and client_name.strip():
        allow.add(client_name.strip())
    return allow


def _load_system_words() -> Optional[set]:
    """Load a system word list for supplemental spell-checking.
    Returns None when no word list is readable (optional supplement, never a requirement)."""
    for cand in SYSTEM_WORDLIST_CANDIDATES:
        p = Path(cand)
        if p.is_file():
            try:
                return set(w.strip().lower() for w in p.read_text().splitlines() if w.strip())
            except Exception:  # noqa: BLE001
                continue
    return None


def _copy_to_text(value) -> str:
    """Coerce slide-copy of any schema shape to a single string (LATENT-FIX 2026-08-31).

    build_deck's slides.schema.json mandates copy = list[str]; check_spelling
    historically treated it as a plain string, so any in-range slide ordinal crashed
    with AttributeError("'list' object has no attribute 'lower'"). Rules:
      - str returned as-is;
      - list joined with " ", keeping its string items; dict-shaped items contribute
        their "text" field when present (tolerated, not schema-mandated);
      - a bare dict contributes its "text" field when present;
      - every other shape degrades to "" so the checker reports per-slide results
        instead of crashing (or silently passing/failing) the whole deck.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                txt = item.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        return " ".join(parts)
    if isinstance(value, dict):
        txt = value.get("text")
        return txt if isinstance(txt, str) else ""
    return ""

def _normalise(text: str) -> str:
    """Normalise a string to lowercase alphanumerics for substring comparison.
    Non-string shapes (schema-mandated list copy, dict copy, None) are coerced via
    _copy_to_text; unknown shapes degrade to "" — never a crash."""
    if not isinstance(text, str):
        text = _copy_to_text(text)
    return _NON_ALNUM.sub("", text.lower())


def _get_renders(run_dir: Path) -> list:
    """Return sorted list of slide-*.png paths in run_dir/renders."""
    renders_dir = run_dir / "renders"
    if not renders_dir.is_dir():
        return []
    return sorted(renders_dir.glob("slide-*.png"))


# ── The three checks ─────────────────────────────────────────────────────────

def check_text_fits(run_dir: Path, slides_path: Optional[Path] = None,
                     *, edge_margin_frac: float = TEXT_EDGE_MARGIN_FRAC) -> str:
    """AF-TEXT-OVERFLOW — no word box within edge_margin_frac of any edge, and no
    two word boxes overlapping by more than TEXT_OVERLAP_AREA_FRAC of the smaller box.

    Margins are computed PER AXIS from the real image: margin_x = round(frac * W),
    margin_y = round(frac * H). At the canonical 2K render size that is 41 px and 23 px.

    `edge_margin_frac` defaults to this module's own TEXT_EDGE_MARGIN_FRAC but the
    build_deck.py wrapper (_chk_text_fits) passes
    build_deck.SLIDE_GEOMETRY_EDGE_MARGIN_FRAC explicitly so the two modules' margin
    can never silently diverge.

    Overlap ignores box pairs on the same OCR line_num — adjacent words on one line
    legitimately touch. Deck-level: reports every offending slide, then fails once.

    Returns "" on pass or defer. Defers when run_dir/renders is absent, holds no
    slide-*.png, or the OCR engine is unavailable (provenance-recorded)."""
    _tess, _pil = ocr_engine()
    provenance = {
        "check": "text_fits",
        "engine_available": _tess is not None,
    }
    renders = _get_renders(run_dir)
    if not renders:
        provenance["deferred"] = "no slide-*.png in renders/"
        _write_provenance(run_dir, provenance)
        return ""
    if _tess is None:
        provenance["deferred"] = "OCR engine unavailable"
        _write_provenance(run_dir, provenance)
        return ""

    problems = []

    for png_path in renders:
        slide_id = png_path.stem
        boxes = word_boxes(png_path)
        if not boxes:
            continue
        # Get actual image dimensions
        try:
            from PIL import Image
            im = Image.open(str(png_path))
            W, H = im.size
        except Exception:  # noqa: BLE001
            continue
        margin_x = round(edge_margin_frac * W)
        margin_y = round(edge_margin_frac * H)
        provenance[f"{slide_id}_WxH"] = [W, H]
        provenance[f"{slide_id}_margins"] = [margin_x, margin_y]
        provenance[f"{slide_id}_boxes"] = len(boxes)

        slide_problems = []

        # Check 1: edge proximity — per axis from real image
        for box in boxes:
            left_edge = box["left"] < margin_x
            top_edge = box["top"] < margin_y
            right_edge = (box["left"] + box["width"]) > (W - margin_x)
            bottom_edge = (box["top"] + box["height"]) > (H - margin_y)
            if left_edge or top_edge or right_edge or bottom_edge:
                edges = []
                if left_edge:
                    edges.append("left")
                if top_edge:
                    edges.append("top")
                if right_edge:
                    edges.append("right")
                if bottom_edge:
                    edges.append("bottom")
                slide_problems.append(
                    f"box '{box['text']}' at ({box['left']},{box['top']}) "
                    f"within {edge_margin_frac*100:.0f}% margin on edge(s): {', '.join(edges)}"
                )
        # Check 2: non-same-line overlap
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a["line_num"] == b["line_num"]:
                    continue
                if _boxes_overlap(a, b, W, H):
                    slide_problems.append(
                        f"box '{a['text']}' (line {a['line_num']}) overlaps "
                        f"'{b['text']}' (line {b['line_num']}) "
                        f"by more than {TEXT_OVERLAP_AREA_FRAC*100:.0f}% of smaller box"
                    )

        if slide_problems:
            problems.append(f"AF-TEXT-OVERFLOW: {slide_id}: {'; '.join(slide_problems)}")

    if problems:
        reason = " | ".join(problems)
        provenance["finding"] = reason
        _write_provenance(run_dir, provenance)
        return reason
    provenance["pass"] = True
    _write_provenance(run_dir, provenance)
    return ""


def check_spelling(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """AF-SPELLING — every rendered word is accounted for.

    A token is KNOWN when, after normalising to lowercase alphanumerics, it is a
    substring of the normalised approved-copy blob for its slide, OR appears in the
    per-client proper-noun allowlist, OR appears in the system word list when one is
    readable. The substring test is what absorbs OCR word-merging ("HELLO WORLD" ->
    "HELLOWORLD", measured on this box) and mirrors prompt_gate._text_present
    (prompt_gate.py:529-548), which solves the same problem in the other direction.

    Approved copy per slide comes from slides.json's "copy" field — the same field
    build_deck.py:1319 hands to ocr_readback. The allowlist comes from intake.json:
    proper_nouns | brand.proper_nouns | brand.name | client_name, whichever are present.

    This is the INVERSE of ocr_readback: that check asks "is the approved copy readable?",
    this one asks "did the renderer paint something nobody approved?". Together they
    close both directions.

    Returns "" on pass or defer."""
    _tess, _pil = ocr_engine()
    provenance = {
        "check": "spelling",
        "engine_available": _tess is not None,
    }
    renders = _get_renders(run_dir)
    if not renders:
        provenance["deferred"] = "no slide-*.png in renders/"
        _write_provenance(run_dir, provenance)
        return ""
    if _tess is None:
        provenance["deferred"] = "OCR engine unavailable"
        _write_provenance(run_dir, provenance)
        return ""

    slides_copy = _load_slides_copy(run_dir, slides_path)
    intake_obj = _load_intake(run_dir)
    allowlist = _get_allowlist(intake_obj)
    system_words = _load_system_words()
    provenance["allowlist_size"] = len(allowlist)
    provenance["system_words"] = system_words is not None

    problems = []

    for png_path in renders:
        slide_id = png_path.stem
        boxes = word_boxes(png_path)
        if not boxes:
            continue

        # Build the approved-copy blob for this slide
        slide_index = None
        try:
            slide_index = int(slide_id.split("-")[-1]) - 1
        except (ValueError, IndexError):
            pass
        approved_blob = ""
        if slide_index is not None and 0 <= slide_index < len(slides_copy):
            slide_obj = slides_copy[slide_index]
            if isinstance(slide_obj, dict):
                approved_blob = _copy_to_text(slide_obj.get("copy", ""))
            elif isinstance(slide_obj, str):
                approved_blob = slide_obj
        elif len(slides_copy) == 1 and renders:
            # Single-copy fallback: use the first slide's copy
            slide_obj = slides_copy[0]
            if isinstance(slide_obj, dict):
                approved_blob = _copy_to_text(slide_obj.get("copy", ""))
            elif isinstance(slide_obj, str):
                approved_blob = slide_obj

        norm_approved = _normalise(approved_blob)
        allow_norm = {_normalise(a) for a in allowlist}

        unknown_tokens = []
        for box in boxes:
            token = box["text"].strip()
            norm_token = _normalise(token)
            if not norm_token or len(norm_token) < OCR_MIN_TOKEN_LEN:
                continue
            # Check 1: is it a substring of the approved copy?
            if norm_token in norm_approved:
                continue
            # Check 2: in the allowlist?
            if token.strip() in allowlist or norm_token in allow_norm:
                continue
            # Check 3: in the system word list?
            if system_words is not None and norm_token in system_words:
                continue
            unknown_tokens.append(token)

        if unknown_tokens:
            problems.append(
                f"AF-SPELLING: {slide_id}: unknown tokens: {', '.join(unknown_tokens[:20])}"
            )

    if problems:
        reason = " | ".join(problems)
        provenance["finding"] = reason
        _write_provenance(run_dir, provenance)
        return reason
    provenance["pass"] = True
    _write_provenance(run_dir, provenance)
    return ""


def check_type_size(run_dir: Path, slides_path: Optional[Path] = None,
                    *, pt_floor: float = 18.0, dark: bool = False,
                    pt_reference_height_px: float = PT_REFERENCE_HEIGHT_PX) -> str:
    """AF-TYPE-SIZE-MEASURED — the smallest word-box height on every slide is at least
    the pt floor scaled to that slide's own height.

        floor_px = px_per_pt(H) * (DARK_THEME_BODY_PT_FLOOR if dark else FONT_BODY_PT_FLOOR)

    The floor constants and the dark-theme decision are IMPORTED FROM build_deck (the
    wrapper passes them in) so the measured check and check_font_floor's declared check
    can never disagree about which floor applies. `pt_reference_height_px` defaults to
    this module's own PT_REFERENCE_HEIGHT_PX but the build_deck.py wrapper
    (_chk_type_size) passes build_deck.SLIDE_GEOMETRY_PT_REFERENCE_HEIGHT_PX explicitly
    so the two modules' reference height can never silently diverge either.

    MEASURES the OCR word-box height, which is the only height the engine reports. That
    is >= glyph cap height and <= full ascender-to-descender extent, so it is a
    conservative proxy; the failure message says so explicitly rather than implying a
    glyph measurement.

    Returns "" on pass or defer."""
    _tess, _pil = ocr_engine()
    provenance = {
        "check": "type_size",
        "engine_available": _tess is not None,
        "pt_floor": pt_floor,
        "dark": dark,
    }
    renders = _get_renders(run_dir)
    if not renders:
        provenance["deferred"] = "no slide-*.png in renders/"
        _write_provenance(run_dir, provenance)
        return ""
    if _tess is None:
        provenance["deferred"] = "OCR engine unavailable"
        _write_provenance(run_dir, provenance)
        return ""

    problems = []

    for png_path in renders:
        slide_id = png_path.stem
        boxes = word_boxes(png_path)
        if not boxes:
            provenance[f"{slide_id}_boxes"] = 0
            continue
        # Get actual image dimensions
        try:
            from PIL import Image
            im = Image.open(str(png_path))
            W, H = im.size
        except Exception:  # noqa: BLE001
            continue
        floor_px = px_per_pt(H, pt_reference_height_px) * pt_floor
        provenance[f"{slide_id}_WxH"] = [W, H]
        provenance[f"{slide_id}_derived_floor_px"] = round(floor_px, 2)
        provenance[f"{slide_id}_boxes"] = len(boxes)

        smallest_box = min(boxes, key=lambda b: b["height"])
        smallest_h = smallest_box["height"]
        provenance[f"{slide_id}_smallest_box_px"] = smallest_h

        if smallest_h < floor_px:
            dark_note = f" (dark-theme {pt_floor}pt floor)" if dark else ""
            problems.append(
                f"AF-TYPE-SIZE-MEASURED: {slide_id}: smallest word box "
                f"'{smallest_box['text']}' is {smallest_h} px high, below the "
                f"{pt_floor}pt floor ({floor_px:.2f} px at this render's {H}px height)"
                f"{dark_note}. Note: measured via OCR word-box height (conservative proxy "
                f"for glyph size)."
            )

    if problems:
        reason = " | ".join(problems)
        provenance["finding"] = reason
        _write_provenance(run_dir, provenance)
        return reason
    provenance["pass"] = True
    _write_provenance(run_dir, provenance)
    return ""
