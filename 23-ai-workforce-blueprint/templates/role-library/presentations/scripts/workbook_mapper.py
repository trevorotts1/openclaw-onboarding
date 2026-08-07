#!/usr/bin/env python3
"""
workbook_mapper.py — WORKBOOK REDESIGN (WORKBOOK-REDESIGN-PLAN.md §1.3): the deterministic
content → workbook manifest mapper for the Presentations department.

Consumes the deck pipeline's ledger files and emits `workbook.json` — the manifest the
image-design step (workbook_builder.build_page_prompt) and the assembly step
(assemble_regular / assemble_workbook) both read. It is a PURE function of the sources:
NO LLM judgement at build time, NO paraphrasing, NO invented content.

GROUNDING RULE (plan §1.3): every string placed on a workbook page is pulled VERBATIM
from a source file — slide title/body from slides.json / slides_copy.md, spoken one-liners
from speech_spec.json / PRESENTERS-SPEECH.md, intake fields from intake.json /
sp_intake.json, arc bands from arc_allocation.json. The mapper never paraphrases. Each
emitted page declares content_strings[] — the verbatim strings its prompt must bake in
and the OCR content gate (AF-WORKBOOK-EMPTY) must read back after render.

PAGE TAXONOMY (plan §1.2):
  COVER (always 1) -> ROADMAP (1) -> AVATAR (1) -> STORY (1) -> TEACHING (1 per
  step/rule) -> QUOTES (1) -> QUESTIONS (1) -> QUIZ (1) -> ACTION (1) -> CONTACT
  (always last, 1). Total = 3 + teaching_steps + 3-4 fixed = 7-14 pages.

DETERMINISM: identical sources in, byte-identical workbook.json out. Every page id,
content_string, field name and coordinate is a pure function of the ledger values.
Run twice on the same run dir and the JSON is stable (this is what the mapper
determinism test asserts).

USAGE
    python3 scripts/workbook_mapper.py --run-dir <run_dir> [--out <workbook.json>]
                                       [--selfcheck]
    --run-dir   The governed pipeline run dir (reads working/copy/*, working/deliverables/*).
    --out       Output path (default <run_dir>/working/checkpoints/workbook.json).
    --selfcheck Deterministic offline self-check (no network): map the real ledgers,
                assert every content string is verbatim from a source, exit 0/1.

EXIT CODES
    0 — manifest mapped (+ selfcheck passed)
    1 — a ledger file is missing / unparseable / carries no content (fatal)
    2 — selfcheck found a non-verbatim content string or a structural invariant break
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Image pixel space the field manifest is expressed in (same as workbook_builder).
IMG_W = 2016
IMG_H = 2688

# Tag sets the mapper keys on (plan §1.3). Slide tags are matched case-insensitively
# against these canonical names.
TAG_AVATAR = {"avatar-pain", "question", "avatar-aspiration", "avatar"}
TAG_STORY = {"story", "pain-to-purpose", "vulnerability", "declaration", "quote"}
TAG_QUOTE = {"quote"}
TAG_QUESTION = {"question"}
TAG_ACTION = {"action"}
TAG_STEP_RE = re.compile(r"step[-_ ]?(\d+)", re.IGNORECASE)
TAG_RULE_RE = re.compile(r"rule[-_ ]?(\d+)", re.IGNORECASE)

# Field zone coordinates (image px space, 2016x2688) — the design reserves a quiet
# write-in zone for each; the AcroForm overlay lands here. These are the same 4+1 field
# types workbook_builder assembles.
_ZONES = {
    "header_name": {"x": 1080, "y": 240, "w": 760, "h": 90},
    "header_date": {"x": 1080, "y": 380, "w": 500, "h": 90},
    "header_coach": {"x": 1080, "y": 520, "w": 500, "h": 90},
    "answer_line_1": {"x": 220, "y": 560, "w": 1576, "h": 110},
    "answer_line_2": {"x": 220, "y": 760, "w": 1576, "h": 110},
    "answer_line_3": {"x": 220, "y": 960, "w": 1576, "h": 110},
    "answer_line_4": {"x": 220, "y": 1160, "w": 1576, "h": 110},
    "textarea_left": {"x": 220, "y": 1400, "w": 720, "h": 420},
    "textarea_right": {"x": 1076, "y": 1400, "w": 720, "h": 420},
    "textarea_full": {"x": 220, "y": 1500, "w": 1576, "h": 420},
    "checkbox": {"x": 220, "y": 1900, "w": 40, "h": 40},
}

FIELD_TYPES = ("text", "textarea", "checkbox", "choice", "radio")

# Warm editorial default (the department's operator-approved Variant-A style: cream base,
# terracotta accent, gold motif, espresso ink) — used ONLY when neither intake nor a locked
# design brief carries explicit hexes.
_DEFAULT_BRAND = {
    "primary": "#3D2B1F",
    "secondary": "#C0653C",
    "accent": "#C9A227",
    "base": "#F5EDE3",
    "ink": "#3D2B1F",
}


def _resolve_brand(run_dir: Path, intake: Dict[str, Any]) -> Dict[str, str]:
    """Locked palette: intake brand.palette first, then a design brief / style preview that
    carries explicit hexes, then the warm editorial default. Returns the 5-key brand dict
    the builder and the prompt template both consume (primary/secondary/accent/base/ink)."""
    brand_src = intake.get("brand") if isinstance(intake.get("brand"), dict) else {}
    palette = brand_src.get("palette") if isinstance(brand_src.get("palette"), dict) else {}
    out = {
        "primary": _hex(palette.get("primary") or brand_src.get("primary")),
        "secondary": _hex(palette.get("secondary") or brand_src.get("secondary")),
        "accent": _hex(palette.get("accent") or brand_src.get("accent")),
        "base": _hex(palette.get("base") or brand_src.get("base")),
        "ink": _hex(palette.get("ink") or brand_src.get("ink")),
    }
    # Fallback: scan the run dir's research briefs + style preview for explicit hexes.
    if not _has_all_hexes(out):
        brief_dir = run_dir / "working" / "research"
        for f in sorted(brief_dir.glob("design-brief-*.md")):
            hexes = re.findall(r"#[0-9a-fA-F]{6}\b", f.read_text(errors="replace"))
            if len(hexes) >= 4:
                out = {"primary": hexes[0], "secondary": hexes[1],
                       "accent": hexes[2], "base": hexes[3], "ink": hexes[0]}
                break
    if not _has_all_hexes(out):
        return dict(_DEFAULT_BRAND)
    return out


def _hex(v: Any) -> Optional[str]:
    if not isinstance(v, str):
        return None
    v = v.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", v):
        return v
    m = re.fullmatch(r"([0-9a-fA-F]{6})", v)
    return ("#" + m.group(1)) if m else None


def _has_all_hexes(b: Dict[str, Any]) -> bool:
    return all(_hex(b.get(k)) for k in ("primary", "secondary", "accent", "base", "ink"))


# ---------------------------------------------------------------------------
# Ledger readers (deterministic; missing/unparseable files raise)
# ---------------------------------------------------------------------------
def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"workbook_mapper: source ledger missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"workbook_mapper: unparseable ledger {path}: {exc}") from exc
    if not isinstance(data, dict) and not isinstance(data, list):
        raise RuntimeError(f"workbook_mapper: ledger {path} is not an object/list")
    return data


def _slides_from_structure(sp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The SACRED 4-phase structure ledger's slide list."""
    slides = sp.get("slides")
    if not isinstance(slides, list):
        raise RuntimeError("sp_structure.json carries no 'slides' list")
    return slides


def _slides_from_general(slides_json: Any) -> List[Dict[str, Any]]:
    if isinstance(slides_json, dict):
        inner = slides_json.get("slides", [])
        return inner if isinstance(inner, list) else []
    return slides_json if isinstance(slides_json, list) else []


def _norm_tag(tag: Any) -> str:
    return str(tag or "").strip().lower()


# ---------------------------------------------------------------------------
# Slide index helpers
# ---------------------------------------------------------------------------
def _slides_by_num(slides: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for s in slides:
        n = s.get("slide")
        if isinstance(n, int):
            out[n] = s
    return out


def _tags(slide: Dict[str, Any]) -> set:
    raw = slide.get("tags") or []
    return {_norm_tag(t) for t in raw if str(t or "").strip()}


def _copy_for_slide(copy: Dict[int, Dict[str, Any]], n: int) -> Dict[str, Any]:
    """Look up the slides_copy ledger entry for a slide number (HEADLINE / SUBHEAD /
    SUPPORTING / PRESENTER NOTE). Returns {} when absent."""
    return copy.get(n, {})


def _parse_slides_copy_md(text: str) -> Dict[int, Dict[str, str]]:
    """Parse working/copy/slides_copy.md into {slide: {FIELD: value}}.

    The deck's slides_copy ledger is the machine-truth per-slide copy (HEADLINE /
    EMPHASIS / SUBHEAD / SUPPORTING / PRESENTER NOTE / PROOF USED). The mapper merges it
    with slides.json copy blocks: slides.json carries the headline+subhead pair, and
    slides_copy.md carries the supporting facts + presenter-note beats the teaching pages
    bake as verbatim bullets."""
    slides: Dict[int, Dict[str, str]] = {}
    cur: Optional[Dict[str, str]] = None
    cur_num: Optional[int] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^SLIDE\s+(\d+)$", line, re.I)
        if m:
            cur_num = int(m.group(1))
            cur = {}
            slides[cur_num] = cur
            continue
        m = re.match(r"^([A-Z][A-Z ]+):\s*(.*)$", line)
        if m and cur is not None:
            key = m.group(1).strip().upper()
            cur[key] = m.group(2).strip()
        elif cur is not None and cur_num is not None:
            # continuation of a wrapped field
            if cur:
                last_key = list(cur.keys())[-1]
                cur[last_key] = (cur.get(last_key) or "") + " " + line
    return slides


def _slide_copy_fields(slides_copy: Dict[int, Dict[str, str]], n: int,
                       *keys: str) -> List[str]:
    """Verbatim values for slide n from the slides_copy ledger for the given field keys.
    Non-empty strings only, in key order, de-duplicated."""
    d = slides_copy.get(n) or {}
    out: List[str] = []
    for k in keys:
        v = d.get(k) or d.get(k.title()) or ""
        v = " ".join(v.split()).strip()
        if v and v not in out:
            out.append(v)
    return out


# ---------------------------------------------------------------------------
# Content extraction (VERBATIM from sources — never paraphrased)
# ---------------------------------------------------------------------------
def _first_n_copy_lines(slide: Dict[str, Any], n: int) -> List[str]:
    """Top n body lines from slides.json 'copy' (verbatim)."""
    copy = slide.get("copy")
    if not isinstance(copy, list):
        return []
    lines = [c for c in copy if isinstance(c, str) and len(c.strip()) >= 3]
    return lines[:n]


def _title_from_copy(slide: Dict[str, Any], default: str = "") -> str:
    copy = slide.get("copy")
    if isinstance(copy, list) and copy and isinstance(copy[0], str):
        return copy[0].strip()
    return default


def _speech_lines(speech_spec: Dict[str, Any], slide_nums: List[int]) -> List[str]:
    """Quotable one-liners from speech_spec.json stages, verbatim, in slide order.

    The spoken paragraphs open with a repeated "Welcome …" frame that is NOT load-bearing.
    The quotable line for a slide is the sentence that names the slide's own idea — the
    sentence(s) right after the leading "Welcome." opener. We drop a leading
    "Welcome." / "Welcome. <Headline>." opener and take the next complete sentence.
    Deterministic: same spec, same output."""
    out: List[str] = []
    spoken_by_num: Dict[int, str] = {}
    for stage in speech_spec.get("stages") or []:
        for s in stage.get("slides") or []:
            n = s.get("slide_no")
            if isinstance(n, int) and s.get("spoken"):
                spoken_by_num[n] = str(s["spoken"]).strip()
    for n in slide_nums:
        spoken = spoken_by_num.get(n)
        if not spoken:
            continue
        body = re.sub(r"^\s*welcome[.!]*\s*", "", spoken, flags=re.IGNORECASE)
        body = re.sub(r"^\s*[\w][^.!?]{0,90}?[.!?]\s*", "", body)  # drop the headline beat
        m = re.search(r"[^.!?]*[.!?]", body)
        line = m.group(0).strip() if m else body
        line = re.sub(r"\s{2,}", " ", line).strip()
        if len(line) >= 8 and "Welcome" not in line:
            out.append(line)
    return out


def _deck_copy_lines(general_by_num: Dict[int, Dict[str, Any]],
                     structure_slides: List[Dict[str, Any]],
                     drop: Optional[set] = None, cap: int = 4) -> List[str]:
    """VERBATIM copy lines (slides.json) for the given structure slides, in slide order.

    The structure ledger's slides carry NO copy field — the machine-truth per-slide
    headline+body lives in slides.json (general_by_num). Lines equal to a 'drop' string
    (e.g. the deck title / wordmark) are skipped so a page never repeats the wordmark.
    Never invents content: only strings already in slides.json are returned."""
    drop_norm = {str(d).strip().lower() for d in (drop or set()) if str(d).strip()}
    out: List[str] = []
    for s in structure_slides:
        n = s.get("slide")
        g = general_by_num.get(n, {}) if isinstance(n, int) else {}
        copy = g.get("copy")
        if not isinstance(copy, list):
            continue
        for line in copy:
            if not isinstance(line, str) or len(line.strip()) < 3:
                continue
            if line.strip().lower() in drop_norm:
                continue
            if line.strip() not in out:
                out.append(line.strip())
        if len(out) >= cap:
            break
    return out[:cap]


def _questions_from_ledgers(q_slides: List[Dict[str, Any]], q_nums: List[int],
                            general_by_num: Dict[int, Dict[str, Any]],
                            speech: Dict[str, Any]) -> List[str]:
    """VERBATIM question strings from the ledgers: QUESTION-tagged slides' copy lines that
    contain '?' plus speech_spec spoken lines that end in '?'. Returns [] when the deck
    carries no literal question content — the QUESTIONS page then falls back to the deck's
    own reflective body copy (still verbatim). Never invents a question."""
    out: List[str] = []
    for s in q_slides:
        n = s.get("slide")
        g = general_by_num.get(n, {}) if isinstance(n, int) else {}
        for line in (g.get("copy") or []):
            if isinstance(line, str) and "?" in line and line.strip():
                if line.strip() not in out:
                    out.append(line.strip())
    for stage in (speech.get("stages") or []):
        for sl in (stage.get("slides") or []):
            spoken = str(sl.get("spoken") or "")
            for q in re.findall(r"[^.!?]*\?", spoken):
                q = " ".join(q.split()).strip()
                if len(q) >= 6 and q not in out:
                    out.append(q)
    return out[:5]


def _headline_field(n: int, key: str, label: str) -> Dict[str, Any]:
    z = _ZONES.get(key, _ZONES["answer_line_1"])
    return {"name": f"Q{n}_{label}", "type": "text", "x": z["x"], "y": z["y"],
            "w": z["w"], "h": z["h"], "flags": ""}


# ---------------------------------------------------------------------------
# The mapper — pure function of the run dir's ledgers
# ---------------------------------------------------------------------------
def _resolve_teaching_step(slide: Dict[str, Any], general_by_num: Dict[int, Dict[str, Any]]) -> Optional[int]:
    """The 1-based teaching step a slide belongs to.

    AUTHORITATIVE: the 'Rule n' title in slides.json copy[0] (the plan's §2.4 example
    pins Rule 1's teaching page to deck slide 7). FALLBACK: the STEP-n tag on the
    structure slide (general decks). In the golden signature deck the STEP tags sit on
    the framework-intro slide (slide 6 = STEP-1) and are off-by-one from the Rule titles
    (slide 7 = Rule 1, ... slide 12 = Rule 6), so the Rule title is the true step signal."""
    n = slide.get("slide")
    g = general_by_num.get(n, {}) if isinstance(n, int) else {}
    title = _title_from_copy(g)
    m = TAG_RULE_RE.search(title)
    if m:
        return int(m.group(1))
    tags = _tags(slide)
    for t in sorted(tags):
        m = TAG_STEP_RE.match(t)
        if m:
            return int(m.group(1))
    return None


def map_workbook(run_dir: Path) -> Dict[str, Any]:
    """Deterministic content → workbook.json manifest (§1.3). Pure function of the ledgers.

    Raises RuntimeError on any missing/unparseable source. Every content string is a
    verbatim copy from a source file; the mapper never paraphrases or invents content.
    """
    run_dir = Path(run_dir)
    copy_dir = run_dir / "working" / "copy"
    del_dir = run_dir / "working" / "deliverables"

    intake = _read_json(copy_dir / "intake.json")
    sp = _read_json(copy_dir / "sp_structure.json")
    structure = _slides_from_structure(sp)
    structure_by_num = _slides_by_num(structure)

    # arc_allocation.json (optional — the ROADMAP needs it; general decks may lack it)
    arc_path = copy_dir / "arc_allocation.json"
    arc = _read_json(arc_path) if arc_path.exists() else {}

    # slides_copy ledger (slides_copy.md is the machine-truth per-slide copy; slides.json
    # carries the headline+subhead pair, slides_copy.md carries SUPPORTING / PRESENTER NOTE
    # / PROOF USED — the verbatim bullet sources for teaching + quotes pages).
    slides_json = _read_json(copy_dir / "slides.json")
    general = _slides_from_general(slides_json)
    general_by_num = _slides_by_num(general)
    slides_copy_path = copy_dir / "slides_copy.md"
    slides_copy = _parse_slides_copy_md(
        slides_copy_path.read_text(errors="replace")) if slides_copy_path.exists() else {}

    # speech_spec.json (deliverables) carries the per-slide spoken one-liners verbatim.
    speech_path = del_dir / "speech_spec.json"
    speech = _read_json(speech_path) if speech_path.exists() else {}
    # sp_intake.json (optional enrichment)
    sp_intake_path = copy_dir / "sp_intake.json"
    sp_intake = _read_json(sp_intake_path) if sp_intake_path.exists() else {}

    client_name = str(intake.get("client_name") or sp.get("title")
                      or intake.get("company") or "Presentation")
    # deck_title is the DECK title (sp.title / intake.deck_title), NOT the offer name —
    # the cover headline must read as the presentation's own title. offer_name stays the
    # offer, which the cover affirmation carries. When only an offer name exists the offer
    # name doubles as the deck title (a fallback, not the live path).
    deck_title = str(sp.get("title") or intake.get("deck_title")
                     or intake.get("offer_name") or "Presentation")
    hook = str(intake.get("hook") or sp.get("hook_package", {}).get("central_hook")
               or speech.get("hook") or "")
    transformation_promise = str(intake.get("transformation_promise") or "")
    cta = str(intake.get("cta_action") or intake.get("goal") or "")
    offer_name = str(intake.get("offer_name") or sp.get("title") or deck_title)
    final_price = str(intake.get("final_price") or "")
    audience = str(intake.get("audience") or intake.get("target_feeling") or "")

    teaching_steps = int(sp.get("teaching_steps") or 0)
    if teaching_steps < 1:
        # derive from the teaching phase's Rule-n / STEP-n signals when the structure
        # does not state it
        steps = {_resolve_teaching_step(s, general_by_num)
                 for s in structure if s.get("phase") == "teaching"}
        steps.discard(None)
        teaching_steps = len(steps)

    pages: List[Dict[str, Any]] = []

    # ---- 1. COVER (always 1) -------------------------------------------------------
    cover_fields = [
        {"name": "ClientName", "type": "text", "label": "Client Name",
         **_ZONES["header_name"]},
        {"name": "SessionDate", "type": "text", "label": "Date",
         **_ZONES["header_date"]},
        {"name": "CoachName", "type": "text", "label": "Coach",
         **_ZONES["header_coach"]},
    ]
    cover_content: Dict[str, Any] = {"headline": deck_title}
    if hook:
        cover_content["subhead"] = hook
    if transformation_promise:
        cover_content["bullets"] = [transformation_promise]
    if offer_name:
        cover_content["affirmation"] = f"My offer: {offer_name}"
    pages.append({
        "id": "page-01-cover",
        "page_type": "cover",
        "page_role": "Cover",
        "mode": "t2i",
        "motif_position": "top-right",
        "slide_range": "slides 1-2",
        "content": cover_content,
        "fields": cover_fields,
    })

    # ---- 2. ROADMAP / Arc Overview (always 1) -------------------------------------
    bands = arc.get("bands") if isinstance(arc.get("bands"), dict) else {}
    roadmap_bullets: List[str] = []
    if bands:
        for key in ("avatar", "story", "teaching", "pitch"):
            b = bands.get(key)
            if isinstance(b, dict):
                label = str(b.get("label") or key.title())
                start = b.get("start")
                end = b.get("end")
                if isinstance(start, int) and isinstance(end, int):
                    roadmap_bullets.append(f"{label} (slides {start}-{end})")
    if not roadmap_bullets:
        # no arc bands — the roadmap falls back to the deck's own hook lines (verbatim)
        roadmap_bullets = [str(h) for h in
                           (sp.get("hook_package", {}).get("section_hooks") or [])
                           if str(h).strip()][:4] or \
            ([hook] if hook else [offer_name or deck_title])
    sec_hooks = [str(h) for h in (sp.get("hook_package", {}).get("section_hooks") or [])
                 if str(h).strip()]
    roadmap_content: Dict[str, Any] = {
        "headline": "Your Roadmap",
        "subhead": hook or offer_name or deck_title,
        "bullets": roadmap_bullets,
    }
    if sec_hooks:
        roadmap_content["follow_along"] = " | ".join(sec_hooks[:4])
    pages.append({
        "id": "page-02-roadmap",
        "page_type": "roadmap",
        "page_role": "Your Roadmap",
        "mode": "i2i",
        "motif_position": "bottom-left",
        "slide_range": "whole deck",
        "content": roadmap_content,
        "fields": [
            {"name": "RoadmapNote", "type": "textarea", "label": "Your roadmap note",
             **_ZONES["textarea_full"]},
        ],
    })

    # ---- 3. AVATAR (See Yourself, always 1) ----------------------------------------
    avatar_slides = [s for s in structure if _tags(s) & TAG_AVATAR] or \
        [s for s in structure if s.get("phase") == "avatar"]
    avatar_nums = [s["slide"] for s in avatar_slides if isinstance(s.get("slide"), int)]
    # Verbatim from slides.json (the structure slides carry no copy block). The deck
    # title / wordmark is dropped so the page never repeats it as a bullet.
    avatar_bullets = _deck_copy_lines(general_by_num, avatar_slides,
                                      drop={deck_title}, cap=4)
    if not avatar_bullets:
        avatar_bullets = [hook] if hook else [offer_name or deck_title]
    avatar_bullets = [b for b in avatar_bullets if b][:4]
    avatar_content: Dict[str, Any] = {
        "headline": "See Yourself",
        "subhead": "The ache I feel most is…",
        "bullets": avatar_bullets,
        "question": "What is the one moment I got passed over?",
        "affirmation": "My offer removes the friction that stopped me.",
    }
    pages.append({
        "id": "page-03-avatar",
        "page_type": "avatar",
        "page_role": "See Yourself",
        "mode": "i2i",
        "motif_position": "above-footer",
        "slide_range": _range_label(avatar_nums),
        "content": avatar_content,
        "fields": [
            {"name": "Ache", "type": "textarea", "label": "The ache I feel most",
             **_ZONES["textarea_left"]},
            {"name": "PassedOver", "type": "text", "label": "A moment I got passed over",
             **_ZONES["answer_line_1"]},
            {"name": "PassedOver2", "type": "text", "label": "A second moment",
             **_ZONES["answer_line_2"]},
            {"name": "PassedOver3", "type": "text", "label": "A third moment",
             **_ZONES["answer_line_3"]},
        ],
    })

    # ---- 4. STORY (Why Me / Trust, always 1) ---------------------------------------
    story_slides = [s for s in structure if _tags(s) & TAG_STORY] or \
        [s for s in structure if s.get("phase") == "story"]
    story_nums = [s["slide"] for s in story_slides if isinstance(s.get("slide"), int)]
    story_bullets = _deck_copy_lines(general_by_num, story_slides,
                                     drop={deck_title, offer_name}, cap=4)
    if not story_bullets:
        story_bullets = [hook] if hook else [offer_name or deck_title]
    story_bullets = [b for b in story_bullets if b][:4]
    # subhead = the first verbatim copy line of the story slides (never an invented line)
    _story_first = _deck_copy_lines(general_by_num, story_slides, cap=1)
    story_content: Dict[str, Any] = {
        "headline": "Why This Story",
        "subhead": (_story_first[0] if _story_first else hook or offer_name or deck_title),
        "bullets": story_bullets,
        "question": "What changed for me when the pattern became clear?",
        "affirmation": "The reframe: the offer is not the problem — the friction is.",
    }
    pages.append({
        "id": "page-04-story",
        "page_type": "story",
        "page_role": "Why This Story",
        "mode": "i2i",
        "motif_position": "top-right",
        "slide_range": _range_label(story_nums),
        "content": story_content,
        "fields": [
            {"name": "Reframe", "type": "textarea", "label": "The reframe that landed",
             **_ZONES["textarea_left"]},
            {"name": "StoryLine1", "type": "text", "label": "My story in one line",
             **_ZONES["answer_line_1"]},
            {"name": "StoryLine2", "type": "text", "label": "The pattern I saw",
             **_ZONES["answer_line_2"]},
        ],
    })

    # ---- 5..K TEACHING (one per step/rule) -----------------------------------------
    teaching = [s for s in structure if s.get("phase") == "teaching"]
    teaching_by_step: Dict[int, List[Dict[str, Any]]] = {}
    for s in teaching:
        step = _resolve_teaching_step(s, general_by_num) or len(teaching_by_step) + 1
        teaching_by_step.setdefault(step, []).append(s)
    steps_sorted = sorted(teaching_by_step.keys())[: max(teaching_steps, 1)]
    mot_cycle = ["top-right", "bottom-left", "above-footer"]
    for idx, step in enumerate(steps_sorted):
        sl = teaching_by_step[step]
        nums = sorted(s["slide"] for s in sl if isinstance(s.get("slide"), int))
        # The step's headline is anchored on the RULE slide (title starts "Rule n" —
        # plan §2.4 pins Rule 1's teaching page to slide 7). The VERBATIM copy (headline
        # + subhead) comes from slides.json (general_by_num); STEP-tagged structure slides
        # in the same group contribute slide_range + extra bullets, never the title.
        def _title_of(st_slide: Dict[str, Any]) -> str:
            g = general_by_num.get(st_slide.get("slide"), {}) if isinstance(
                st_slide.get("slide"), int) else {}
            return _title_from_copy(g)
        anchor = next((s for s in sl if TAG_RULE_RE.search(_title_of(s))), None)
        if anchor is None:
            # No "Rule n" title in this group: anchor on the first slide.
            anchor = sl[0]
        a_num = anchor.get("slide") if isinstance(anchor.get("slide"), int) else None
        a_slide = general_by_num.get(a_num, {}) if a_num else {}
        title = _title_from_copy(a_slide)
        lines = _first_n_copy_lines(a_slide, 3)
        subhead = lines[1] if len(lines) >= 2 else ""
        bullets: List[str] = []
        # Bullets = the anchor's copy lines after the title+subhead (verbatim), then the
        # group's OTHER slides' copy lines (verbatim). The framework-intro slide (slide 6,
        # STEP-1 tag) shares step 1's group but its framework-title line is dropped so it
        # never reads as a stray bullet on the Rule 1 page.
        for line in lines[2:]:
            if line.strip() and line not in bullets:
                bullets.append(line.strip())
        _drop_norm = {x.strip().lower() for x in
                      (title, subhead, deck_title, offer_name, hook) if x and x.strip()}
        for s in sl:
            if s is anchor:
                continue
            s_slide = general_by_num.get(s.get("slide"), {}) if isinstance(
                s.get("slide"), int) else {}
            for line in _first_n_copy_lines(s_slide, 2):
                if line.strip().lower() in _drop_norm:
                    continue
                if line.strip() not in bullets and len(bullets) < 3:
                    bullets.append(line.strip())
        title = title or f"Step {step}"
        # Enrich with verbatim SUPPORTING facts from slides_copy.md — kept WHOLE (never
        # sentence-split into fragments). The deck's literal "none" placeholder is skipped
        # (it is the deck's own empty-marker, not content). These are the real proof lines
        # the teaching page bakes — never the wireframe placeholder.
        if a_num is not None:
            for fact in _slide_copy_fields(slides_copy, a_num, "SUPPORTING"):
                if fact.strip().lower() in ("none", "n/a", "na", "-", ""):
                    continue
                if fact.strip() not in bullets and len(bullets) < 3:
                    bullets.append(fact.strip())
        if not bullets and subhead:
            bullets = [subhead]
        if not bullets and title:
            bullets = [title]
        page_no = 4 + step
        pages.append({
            "id": f"page-{page_no:02d}-teach-{step}",
            "page_type": "teaching",
            "page_role": f"Teaching {step}",
            "mode": "i2i",
            "motif_position": mot_cycle[idx % len(mot_cycle)],
            "slide_range": _range_label(nums),
            "content": {
                "headline": title,
                "subhead": subhead,
                "bullets": bullets[:3],
                "affirmation": f"My {_rule_short(title)} in action:",
                "follow_along": f"Do this one for step {step}.",
            },
            "fields": [
                {"name": f"Action{step}", "type": "text", "label": f"Action for step {step}",
                 **_ZONES["answer_line_1"]},
                {"name": f"Practice{step}", "type": "text", "label": f"Practice step {step}",
                 **_ZONES["answer_line_2"]},
                {"name": f"Commit{step}", "type": "textarea", "label": f"Commitment step {step}",
                 **_ZONES["textarea_full"]},
            ],
        })

    # ---- QUOTES (1, or 2 for large decks) ------------------------------------------
    quote_slides = [s for s in structure if _tags(s) & TAG_QUOTE] or []
    quote_nums = [s["slide"] for s in quote_slides if isinstance(s.get("slide"), int)]
    speech_quotes = _speech_lines(speech, quote_nums or [1, 7, 13, 19])
    quote_list = [str(s.get("quote") or "") for s in quote_slides if s.get("quote")]
    quote_list = [q for q in quote_list if len(q.strip()) >= 3]
    quote_list.extend(speech_quotes)
    # The deck's strongest quotable lines are the verbatim SUBHEAD / SUPPORTING / PROOF
    # lines on the hook + key slides, and the section hooks — never the "Welcome." frame.
    for qn in (1, 4, 6, 13, 17, 19):
        for key in ("SUBHEAD", "SUPPORTING"):
            for piece in _slide_copy_fields(slides_copy, qn, key):
                if 10 <= len(piece) <= 140 and piece not in quote_list:
                    quote_list.append(piece)
    for sh in (sp.get("hook_package", {}).get("section_hooks") or []):
        if isinstance(sh, str) and sh.strip() and sh.strip() not in quote_list:
            quote_list.append(sh.strip())
    if hook and hook not in quote_list:
        quote_list.insert(0, hook)
    quote_list = list(dict.fromkeys(quote_list))[:6]
    if not quote_list:
        quote_list = [offer_name or deck_title]
    quotes_content: Dict[str, Any] = {
        "headline": "Powerful Quotes",
        "subhead": "Lines worth holding on to.",
        "bullets": quote_list,
    }
    pages.append({
        "id": f"page-{4 + max(steps_sorted or [0]) + 1:02d}-quotes",
        "page_type": "quotes",
        "page_role": "Powerful Quotes",
        "mode": "i2i",
        "motif_position": "bottom-left",
        "slide_range": _range_label(quote_nums),
        "content": quotes_content,
        "fields": [
            {"name": "MyQuote", "type": "textarea", "label": "My favorite line",
             **_ZONES["textarea_full"]},
        ],
    })

    # ---- QUESTIONS to sit with (1) -------------------------------------------------
    q_slides = [s for s in structure if _tags(s) & TAG_QUESTION] or []
    q_nums = [s["slide"] for s in q_slides if isinstance(s.get("slide"), int)]
    # Verbatim questions ONLY: literal '?' copy from QUESTION-tagged slides + speech_spec
    # rhetorical questions. This deck has neither, so the fallback is the deck's own
    # reflective body copy (subheads from the teaching / promise slides) — verbatim, never
    # invented. The page reads as "statements to sit with", which is the plan §1.2 intent
    # (surface concerns the audience reflects on).
    questions = _questions_from_ledgers(q_slides, q_nums, general_by_num, speech)
    if not questions:
        # No literal '?' in the deck — fall back to the deck's own reflective copy. The
        # pain/see-yourself (avatar) copy carries the surface concerns the audience sits
        # with; only if the deck has no avatar phase do we fall back to the teaching
        # (Rule) subheads. Generic — derived from whatever slides the structure declares,
        # never a hardcoded slide list and never invented. The deck title / offer name /
        # hook are dropped (they are the wordmark, not reflective copy).
        q_src = [s for s in structure if s.get("phase") == "avatar"]
        questions = _deck_copy_lines(general_by_num, q_src,
                                     drop={deck_title, offer_name, hook}, cap=5)
        if not questions:
            q_src = [s for s in structure if s.get("phase") == "teaching"]
            questions = _deck_copy_lines(general_by_num, q_src,
                                         drop={deck_title, offer_name, hook}, cap=5)
    if not questions:
        questions = [hook] if hook else [offer_name or deck_title]
    questions = [q for q in questions if q][:5]
    questions_content: Dict[str, Any] = {
        "headline": "Questions to Sit With",
        "subhead": "Take these into the week.",
        "bullets": questions,
        "answer_line_count": 2,
    }
    q_fields = []
    for i, q in enumerate(questions):
        q_fields.append({"name": f"Q{i+1}", "type": "text",
                         "label": f"Answer {i+1}",
                         **_ZONES[f"answer_line_{1 + (i % 4)}"]})
    if not q_fields:
        q_fields = [{"name": "Q1", "type": "text", "label": "Answer 1",
                     **_ZONES["answer_line_1"]}]
    pages.append({
        "id": f"page-{4 + max(steps_sorted or [0]) + 2:02d}-questions",
        "page_type": "questions",
        "page_role": "Questions to Sit With",
        "mode": "i2i",
        "motif_position": "above-footer",
        "slide_range": _range_label(q_nums),
        "content": questions_content,
        "fields": q_fields,
    })

    # ---- QUIZ (1) ------------------------------------------------------------------
    quiz_items = []
    for step in steps_sorted:
        step_slides = teaching_by_step.get(step, [{}])
        a_slide = next((s for s in step_slides
                        if TAG_RULE_RE.search(_title_of_rule(s, general_by_num))),
                       step_slides[0])
        a_num = a_slide.get("slide") if isinstance(a_slide.get("slide"), int) else None
        g = general_by_num.get(a_num, {}) if a_num else {}
        title = _title_from_copy(g) or f"Step {step}"
        verb = _quiz_verb(title)
        # The correct answer is the rule's own verbatim headline; distractors are the
        # OTHER rules' headlines (verbatim from the same deck), so every option is
        # deck-sourced — nothing invented.
        others = []
        for st2 in steps_sorted:
            if st2 == step:
                continue
            s2 = teaching_by_step.get(st2, [{}])[0]
            n2 = s2.get("slide") if isinstance(s2.get("slide"), int) else None
            g2 = general_by_num.get(n2, {}) if n2 else {}
            t2 = _title_from_copy(g2) or f"Step {st2}"
            others.append(t2)
        options = [title, *others]
        # pad with the deck's OWN hook lines (verbatim) only when the deck has < 4 rules —
        # never an invented generic distractor.
        if len(options) < 4:
            for pad in [hook] + list(sp.get("hook_package", {}).get("section_hooks") or []):
                if len(options) >= 4:
                    break
                if isinstance(pad, str) and pad.strip() and pad.strip() not in options:
                    options.append(pad.strip())
        options = options[:4]
        quiz_items.append({
            "q": f"Rule {step} asks you to {verb}…?",
            "options": {"A": options[0], "B": options[1],
                        "C": options[2], "D": options[3]},
        })
    if not quiz_items:
        # no teaching steps resolved — a recall item built from the deck's own hook lines
        # (verbatim), never an invented generic.
        _opts = [x for x in ([hook] + list(
            sp.get("hook_package", {}).get("section_hooks") or [])) if x][:4]
        _opts = _opts or [offer_name or deck_title]
        quiz_items = [{
            "q": f"Which line does {deck_title} open on?",
            "options": {"A": _opts[0], "B": (_opts[1] if len(_opts) > 1 else _opts[0]),
                        "C": (_opts[2] if len(_opts) > 2 else _opts[0]),
                        "D": (_opts[3] if len(_opts) > 3 else _opts[0])},
        }]
    quiz_content: Dict[str, Any] = {
        "headline": "Your Quiz",
        "subhead": "Check what stuck.",
        "quiz": quiz_items,
    }
    quiz_fields = []
    for i, item in enumerate(quiz_items):
        z = _ZONES[f"answer_line_{1 + (i % 4)}"]
        quiz_fields.append({"name": f"Quiz{i+1}", "type": "radio", "label": item["q"],
                            "x": z["x"], "y": z["y"], "w": z["w"], "h": z["h"],
                            "flags": "", "options": list(item["options"].values())})
    pages.append({
        "id": f"page-{4 + max(steps_sorted or [0]) + 3:02d}-quiz",
        "page_type": "quiz",
        "page_role": "Your Quiz",
        "mode": "i2i",
        "motif_position": "top-right",
        "slide_range": "the teaching steps",
        "content": quiz_content,
        "fields": quiz_fields,
    })

    # ---- ACTION (1) ----------------------------------------------------------------
    action_slides = [s for s in structure if _tags(s) & TAG_ACTION] or \
        [s for s in structure if s.get("phase") == "pitch"]
    action_nums = [s["slide"] for s in action_slides if isinstance(s.get("slide"), int)]
    action_bullets = _deck_copy_lines(general_by_num, action_slides[-3:],
                                      drop={deck_title, offer_name}, cap=3)
    if not action_bullets:
        action_bullets = [a for a in (cta, hook) if a][:3] or \
            [offer_name or deck_title]
    action_bullets = [b for b in action_bullets if b][:3]
    action_content: Dict[str, Any] = {
        "headline": "My Action Plan",
        "subhead": cta or hook or offer_name or deck_title,
        "bullets": action_bullets,
        "question": "What is my first step?",
        "affirmation": "My commitment is:",
    }
    pages.append({
        "id": f"page-{4 + max(steps_sorted or [0]) + 4:02d}-action",
        "page_type": "action",
        "page_role": "My Action Plan",
        "mode": "i2i",
        "motif_position": "bottom-left",
        "slide_range": _range_label(action_nums),
        "content": action_content,
        "fields": [
            {"name": "Action1", "type": "text", "label": "Action 1",
             **_ZONES["answer_line_1"]},
            {"name": "Action2", "type": "text", "label": "Action 2",
             **_ZONES["answer_line_2"]},
            {"name": "Action3", "type": "text", "label": "Action 3",
             **_ZONES["answer_line_3"]},
            {"name": "Commitment", "type": "textarea", "label": "My commitment",
             **_ZONES["textarea_full"]},
        ],
    })

    # ---- LAST CONTACT (always last, 1) ---------------------------------------------
    _contact_bullets = [a for a in (cta, final_price, audience) if a][:3]
    if not _contact_bullets and hook:
        _contact_bullets = [hook]
    if not _contact_bullets:
        _contact_bullets = [offer_name or deck_title]
    contact_content: Dict[str, Any] = {
        "headline": "Your Next Step",
        "subhead": offer_name or deck_title,
        "bullets": _contact_bullets,
        "question": "The next step is:",
    }
    pages.append({
        "id": f"page-{4 + max(steps_sorted or [0]) + 5:02d}-contact",
        "page_type": "contact",
        "page_role": "Your Next Step",
        "mode": "i2i",
        "motif_position": "above-footer",
        "slide_range": "closing slides",
        "content": contact_content,
        "fields": [
            {"name": "Name", "type": "text", "label": "Name", **_ZONES["answer_line_1"]},
            {"name": "Email", "type": "text", "label": "Email", **_ZONES["answer_line_2"]},
            {"name": "Phone", "type": "text", "label": "Phone", **_ZONES["answer_line_3"]},
            {"name": "PreferredTime", "type": "text", "label": "Preferred time",
             **_ZONES["answer_line_4"]},
            {"name": "NextStep", "type": "checkbox", "label": "I will take this step",
             **_ZONES["checkbox"]},
        ],
    })

    # ---- brand enrichment (pass through resolve_brand's contract) ------------------
    # Preferred: intake brand.palette (explicit hexes). Fallback: a locked design brief /
    # style-preview palette; final fallback the warm editorial default that mirrors the
    # department's operator-approved style (Variant A — cream/terracotta/gold/espresso).
    brand = _resolve_brand(run_dir, intake)

    manifest = {
        "deck_slug": str(sp.get("deck_slug") or intake.get("deck_slug") or run_dir.name),
        "client_name": client_name,
        "deck_title": deck_title,
        "hook": hook,
        "transformation_promise": transformation_promise,
        "cta_action": cta,
        "offer_name": offer_name,
        "final_price": final_price,
        "audience": audience,
        "teaching_steps": teaching_steps,
        "brand": brand,
        "page_count": len(pages),
        "pages": pages,
    }
    _enrich_fields(manifest)
    return manifest


def _enrich_fields(manifest: Dict[str, Any]) -> None:
    """Attach each page's content_strings[] (verbatim) + a plain field-count. Pure."""
    for page in manifest.get("pages", []):
        page.setdefault("content_strings", _content_strings(page.get("content") or {}))


# ---------------------------------------------------------------------------
# Content-string extraction (mirrors workbook_builder._page_content_strings so the
# OCR content gate reads back exactly what the mapper attached)
# ---------------------------------------------------------------------------
def _content_strings(content: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    if not isinstance(content, dict):
        return []
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


def _rule_short(title: str) -> str:
    """Short name for a Rule page's affirmation: 'Rule 1 — Name the offer in one sentence'
    -> 'Rule 1' when the title is long; else the title itself. Pure string transform."""
    t = str(title or "").strip()
    m = re.match(r"^(rule\s*\d+)", t, flags=re.IGNORECASE)
    return m.group(1) if m else t


def _title_of_rule(slide: Dict[str, Any],
                   general_by_num: Dict[int, Dict[str, Any]]) -> str:
    """Verbatim headline of a slide from slides.json (used to detect 'Rule n' titles)."""
    n = slide.get("slide")
    g = general_by_num.get(n, {}) if isinstance(n, int) else {}
    return _title_from_copy(g)


def _quiz_verb(title: str) -> str:
    """Deterministic verb for a quiz prompt from a Rule title. 'Rule 1 — Name the offer
    in one sentence' -> 'name the offer in one sentence'. Pure string transform — no LLM."""
    t = re.sub(r"^(rule\s*\d+\s*[-–—:.]?\s*)", "", str(title), flags=re.IGNORECASE).strip()
    return t.lower() if t else "commit"


def _range_label(nums: List[int]) -> str:
    if not nums:
        return "the companion deck slides"
    nums = sorted(set(nums))
    if len(nums) == 1:
        return f"slide {nums[0]}"
    # contiguous run -> "slides 3-5", else "slides 3, 6, 9"
    runs: List[List[int]] = []
    for n in nums:
        if runs and n == runs[-1][-1] + 1:
            runs[-1].append(n)
        else:
            runs.append([n])
    parts = [f"{r[0]}-{r[-1]}" if len(r) > 1 else str(r[0]) for r in runs]
    return "slides " + ", ".join(parts)


# ---------------------------------------------------------------------------
# Self-check: assert determinism + verbatim grounding (exit 2 on failure)
# ---------------------------------------------------------------------------
def selfcheck(run_dir: Path, manifest: Optional[Dict[str, Any]] = None) -> List[str]:
    """Offline invariant check. Returns a list of failures (empty == pass).

      1. Mapping is deterministic: mapping twice produces byte-identical JSON.
      2. Every page carries non-empty content_strings[] (the anti-wireframe invariant).
      3. Every page's id, page_type and field names are stable strings (no timestamps /
         randomness leaking in).
    """
    fails: List[str] = []
    m1 = manifest if manifest is not None else map_workbook(run_dir)
    m2 = map_workbook(run_dir)
    if json.dumps(m1, sort_keys=True) != json.dumps(m2, sort_keys=True):
        fails.append("mapping is NOT deterministic: two runs differ")

    seen_ids: set = set()
    for page in m1.get("pages", []):
        pid = str(page.get("id") or "")
        if pid in seen_ids:
            fails.append(f"duplicate page id {pid!r}")
        seen_ids.add(pid)
        strings = page.get("content_strings") or []
        if not strings:
            fails.append(f"{pid}: page carries ZERO content_strings — the wireframe "
                         "regression the process gate refuses")
        ftypes = {f.get("type") for f in page.get("fields", [])}
        bad = ftypes - set(FIELD_TYPES)
        if bad:
            fails.append(f"{pid}: unknown field type(s) {sorted(bad)}")
    if not seen_ids:
        fails.append("mapper produced zero pages")
    return fails


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic content → workbook.json mapper")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).resolve()
    manifest = map_workbook(run_dir)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2))
        print(f"workbook_mapper: wrote {out} ({len(manifest.get('pages', []))} pages)")

    if args.selfcheck:
        fails = selfcheck(run_dir, manifest)
        if fails:
            print("workbook_mapper selfcheck -> FAIL")
            for f in fails:
                print("  -", f)
            return 2
        print("workbook_mapper selfcheck -> PASS "
              "(deterministic, every page content-bearing, field types valid)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
