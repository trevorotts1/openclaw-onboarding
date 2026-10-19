#!/usr/bin/env python3
"""Skill 71 composition library: how a section's photo and words relate.

One module, three jobs, all driven by references/composition-treatments.json
(the single source of truth) and assets/visual-standards/reference-catalog.json
(the typed hosted references):

  1. PROMPTS   treatment resolution by section role, the wireframe / mockup /
               photo prompt sentences, and the typed reference picker the
               stage executor uses.
  2. BUDGET    the per-page composition budget (split at most 40 percent, a
               words-over-image hero, a full-width band, shaped crops, an
               intersecting treatment, no adjacent repeats) computed from a
               section plan or from a built page's geometry.
  3. QC        pure geometry and pixel checks (section classifier, shape
               corner test, light-field test, legibility contrast, face-zone
               test). Pure functions: unit-testable with no browser.

Python 3 stdlib + Pillow (Pillow only for the pixel checks).
"""
from __future__ import annotations

import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
TREATMENTS_PATH = SKILL_ROOT / "references" / "composition-treatments.json"
CATALOG_PATH = SKILL_ROOT / "assets" / "visual-standards" / "reference-catalog.json"

WIREFRAME_STAGES = ("desktop-wireframe", "mobile-tablet")
MOCKUP_STAGES = ("visual-mockup", "final-mockups")
MAX_TYPED_REFERENCES = 3

# Where the copy sits and where the subject sits when a slot declares no zones.
# (copy_side, copy_pct, subject_pct, corner)
ZONE_DEFAULTS = {
    "overlay-light": ("left", 55, 38, "bottom-left"),
    "overlay-dark-scrim": ("left", 40, 45, "bottom-left"),
    "band-over-texture": ("left", 40, 45, "bottom-left"),
    "card-overlaps-photo": ("left", 30, 60, "bottom-left"),
}
DEFAULT_ZONE = ("left", 40, 45, "bottom-left")
# Treatments whose measured section class is knowable from element boxes.
EXPECT_CLASS = {"split": "SPLIT", "overlay-light": "OVERLAY",
                "overlay-dark-scrim": "OVERLAY", "band-over-texture": "OVERLAY"}


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def library() -> dict:
    return json.loads(TREATMENTS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def treatments() -> dict:
    return {t["id"]: t for t in library()["treatments"]}


def treatment_ids() -> list:
    return list(treatments())


def counts_as(treatment_id: str) -> set:
    return set((treatments().get(treatment_id) or {}).get("counts_as") or [])


MEDIA_BASE_ENV = "SKILL71_REFERENCE_MEDIA_BASE"
DEFAULT_MOTIFS = "abstract concentric arcs, small dots and fine grid lines"


def media_base() -> str:
    """Base URL of the operator media-library folder that holds the reference
    sheets, injected at runtime (the catalog stores only each file's path, so the
    library's account identifier is never committed)."""
    return os.environ.get(MEDIA_BASE_ENV, "").strip().rstrip("/")


def load_catalog(path: Path | None = None) -> dict:
    """The reference catalog with every row's url assembled from the injected
    media base and the row's media_path. With no base set the rows carry no url,
    so no hosted reference is attached and the prompt text still carries the
    composition rules."""
    try:
        cat = json.loads((path or CATALOG_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rows": []}
    base = media_base()
    rows = []
    for row in cat.get("rows") or []:
        row = dict(row)
        if row.get("media_path") and not row.get("url"):
            if base:
                row["url"] = base + "/" + str(row["media_path"]).lstrip("/")
        rows.append(row)
    cat["rows"] = rows
    return cat


# --------------------------------------------------------------------------
# brand: composition cues and color tokens
# --------------------------------------------------------------------------
def load_brand(run_dir=None, explicit=None) -> dict:
    """The run's brand file, same order as validate_wireframe.resolve_brand_path:
    explicit path, the run's private/brand.json pin, intake.json brand_file, the
    skill's own brand file. {} when none parses."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if run_dir:
        run_dir = Path(run_dir)
        candidates.append(run_dir / "private" / "brand.json")
        try:
            intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
            bf = intake.get("brand_file") if isinstance(intake, dict) else None
            if bf:
                candidates.append(Path(bf) if Path(bf).is_absolute() else run_dir / bf)
        except (OSError, ValueError):
            pass
    candidates.append(SKILL_ROOT / "assets" / "brand" / "blackceo-brand.json")
    for cand in candidates:
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def composition_cues(brand: dict | None) -> dict:
    """{preferred, forbidden, imagery_direction} from the brand's composition_cues;
    unknown treatment ids are dropped so a typo never silently forbids nothing
    or everything."""
    raw = (brand or {}).get("composition_cues")
    raw = raw if isinstance(raw, dict) else {}
    known = treatments()
    pick = lambda key: [t for t in raw.get(key) or [] if isinstance(t, str) and t in known]  # noqa: E731
    forbidden = set(pick("forbidden"))
    return {"preferred": [t for t in pick("preferred") if t not in forbidden],
            "forbidden": sorted(forbidden),
            "imagery_direction": str(raw.get("imagery_direction") or "").strip()}


def _hex_rgb(value):
    text = str(value or "").strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    return None


def brand_surface_and_ink(brand: dict | None):
    """(surface_rgb, ink_rgb) from the brand's light and dark palette slots
    (cream = light ground, navy = dark ink); None for a slot not yet supplied."""
    palette = (brand or {}).get("palette") or {}
    return _hex_rgb(palette.get("cream")), _hex_rgb(palette.get("navy"))


def line_color(surface, ink, max_ratio: float | None = None):
    """The surface color shifted toward the ink color as far as the light-field
    rule allows: field-to-surface contrast at most max_ratio (default the
    library's field_to_surface_max_ratio less a 0.03 margin)."""
    limit = (max_ratio or library()["thresholds"]["field_to_surface_max_ratio"]) - 0.03
    best = tuple(surface)
    for step in range(1, 101):
        t = step / 100
        mix = tuple(round(s + (i - s) * t) for s, i in zip(surface, ink))
        if contrast_ratio(mix, surface) > limit:
            break
        best = mix
    return best


def _rgb_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


# --------------------------------------------------------------------------
# section roles and default treatments
# --------------------------------------------------------------------------
def section_role(section_id: str, section_name: str = "") -> str | None:
    """The section's role, from its id first, then its printed name."""
    sid = str(section_id or "").strip().lower()
    name = str(section_name or "").strip().lower()
    for role in library()["roles"]:
        if sid and re.search(role["id_regex"], sid):
            return role["role"]
    for role in library()["roles"]:
        if name and re.search(role["name_regex"], name):
            return role["role"]
    return None


def _role_entry(role: str | None) -> dict:
    for entry in library()["roles"]:
        if entry["role"] == role:
            return entry
    return {}


def choose_treatment(role: str | None, previous: str | None, seen_in_role: int = 0,
                     cues: dict | None = None) -> str:
    """Role default, rotated so no two adjacent sections share a non-split
    treatment. The brand's composition cues apply first: a forbidden treatment is
    never chosen and a preferred one in the role's own pool moves to the front."""
    entry = _role_entry(role)
    pool = []
    rotate = entry.get("rotate")
    if rotate:
        pool.append(rotate[seen_in_role % len(rotate)])
    if entry.get("default"):
        pool.append(entry["default"])
    pool += list(entry.get("alternates") or [])
    pool.append(library()["fallback_treatment"])
    cues = cues or {}
    forbidden = set(cues.get("forbidden") or [])
    allowed = [t for t in pool if t not in forbidden]
    pool = allowed or [t for t in ("split", library()["fallback_treatment"]) if t not in forbidden] or pool
    liked = [t for t in cues.get("preferred") or [] if t in pool]
    pool = liked + [t for t in pool if t not in liked]
    for candidate in pool:
        if candidate == "split" or candidate != previous:
            return candidate
    return pool[0]


def _zone(slot: dict, key: str):
    zone = slot.get(key)
    if isinstance(zone, (list, tuple)) and len(zone) == 4:
        try:
            return [float(v) for v in zone]
        except (TypeError, ValueError):
            return None
    return None


def zone_words(slot: dict, treatment_id: str, brand: dict | None = None) -> dict:
    """copy side, subject side, percents and quiet corner for the prompt sentences."""
    side, copy_pct, subject_pct, corner = ZONE_DEFAULTS.get(treatment_id, DEFAULT_ZONE)
    copy_zone, subject_zone = _zone(slot, "copy_zone"), _zone(slot, "subject_zone")
    if copy_zone:
        cx, cy = (copy_zone[0] + copy_zone[2]) / 2, (copy_zone[1] + copy_zone[3]) / 2
        side = "left" if cx < 50 else "right"
        copy_pct = max(1, round(copy_zone[2] - copy_zone[0]))
        corner = ("top" if cy < 50 else "bottom") + "-" + ("left" if cx < 50 else "right")
    if subject_zone:
        subject_pct = max(1, round(subject_zone[2] - subject_zone[0]))
        subject_side = "left" if (subject_zone[0] + subject_zone[2]) / 2 < 50 else "right"
    else:
        subject_side = "right" if side == "left" else "left"
    cues = composition_cues(brand)
    surface, ink = brand_surface_and_ink(brand)
    words = {"copy_side": side, "subject_side": subject_side, "copy_pct": str(copy_pct),
             "subject_pct": str(subject_pct), "corner": corner,
             "motifs": str(slot.get("motifs") or cues["imagery_direction"] or DEFAULT_MOTIFS)}
    if surface and ink:
        words["surface_color"] = _rgb_hex(surface)
        words["line_color"] = _rgb_hex(line_color(surface, ink))
    return words


def _fill(template: str, words: dict) -> str:
    out = template
    for key, value in words.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def assign_treatments(sections: list, cues: dict | None = None) -> list:
    """One resolved record per section, in order. A slot's declared treatment
    wins; a slot without one takes its section role's default, rotated so no
    two adjacent sections repeat a non-split treatment. Returns
    [{section_id, role, slots: [{slot, treatment, source}]}]. A section with
    no slots whose role default is a full-width band carries a section-level
    backdrop record (slot_id None). `cues` is composition_cues(brand): forbidden
    treatments are never picked by a role default."""
    resolved, previous, seen = [], None, {}
    for section in sections:
        if not isinstance(section, dict):
            resolved.append({"section_id": None, "role": None, "slots": []})
            continue
        sid = section.get("section_id")
        role = section_role(sid, section.get("section_name") or "")
        slots = [s for s in (section.get("slots") or []) if isinstance(s, dict)]
        entry = {"section_id": sid, "role": role, "slots": []}
        first_choice = None
        for slot in slots:
            declared = slot.get("treatment")
            if declared in treatments():
                chosen, source = declared, "declared"
            else:
                chosen = first_choice or choose_treatment(role, previous, seen.get(role, 0), cues)
                source = "role-default"
            first_choice = first_choice or (chosen if chosen != "split" else None)
            entry["slots"].append({"slot": slot, "treatment": chosen, "source": source})
        if not slots:
            backdrop = choose_treatment(role, previous, seen.get(role, 0), cues)
            if "band" in counts_as(backdrop):
                entry["slots"].append({"slot": {"slot_id": None}, "treatment": backdrop,
                                       "source": "role-default"})
        seen[role] = seen.get(role, 0) + 1
        primary = next((s["treatment"] for s in entry["slots"] if s["treatment"] != "split"), None)
        previous = primary
        resolved.append(entry)
    return resolved


# --------------------------------------------------------------------------
# prompt sentences
# --------------------------------------------------------------------------
def slot_words(slot: dict, treatment_id: str) -> str:
    """The slot's composition record as one clause for the slot list."""
    t = treatments().get(treatment_id) or {}
    parts = [f"treatment={treatment_id}", f"mask={slot.get('mask') or t.get('mask', 'rect')}"]
    for key in ("copy_zone", "subject_zone"):
        zone = _zone(slot, key)
        if zone:
            parts.append(f"{key}=" + "/".join(str(round(v)) for v in zone) + " percent")
    scrim = slot.get("scrim")
    if isinstance(scrim, dict) and scrim.get("type") not in (None, "none"):
        parts.append(f"scrim={scrim.get('type')} {scrim.get('from_pct', 0)}-{scrim.get('to_pct', 0)} percent")
    return "(" + "; ".join(parts) + ")"


def photo_rules(slot: dict, treatment_id: str, brand: dict | None = None) -> str:
    """The photo-generation sentences for one slot: the treatment's own
    copy-space or crop-safe framing plus the universal negative. Every
    placeholder is filled; a prompt that still holds one raises ValueError, so
    a model is never sent a sentence it cannot act on."""
    t = treatments().get(treatment_id) or {}
    words = zone_words(slot, treatment_id, brand)
    text = (_fill(t.get("photo_prompt", ""), words) + " " + library()["universal_photo_prompt"]).strip()
    left = re.search(r"\{[a-z_]+\}", text)
    if left:
        raise ValueError(f"treatment {treatment_id}: the photo rules still hold {left.group(0)}; the run's brand "
                         "file must supply its light and dark palette colors (cream and navy) before this slot is generated")
    return text


def _label(slot: dict, treatment_id: str) -> str:
    px = slot.get("delivery_px")
    size = ""
    if isinstance(px, dict):
        desktop = px.get("desktop")
        if isinstance(desktop, (list, tuple)) and len(desktop) == 2:
            size = f"{desktop[0]} x {desktop[1]} "
    return f"{slot.get('slot_id')} {size}{slot.get('aspect_ratio') or ''} {treatment_id}".replace("  ", " ").strip()


def typed_reference_text(refs: list, wanted: set | None = None) -> str:
    """Name each attached reference by type; list only the traits that match
    a treatment this section actually uses (never advertise `split`)."""
    if not refs:
        return ""
    roles = {"wireframe": "a wireframe sheet (structure and labelling only)",
             "hybrid-image-map": "an image-map sheet (structure and slot labelling only)",
             "mockup": "a finished mockup (finish and look only)",
             "mood-board": "a mood board (brand direction only)",
             "mockup-crop": "a cropped band from a real page (composition technique only)"}
    named = []
    for ref in refs:
        text = roles.get(ref.get("type"), "a reference sheet (look only)")
        traits = [t for t in ref.get("traits") or []
                  if t in treatments() and t != "split" and (wanted is None or t in wanted)]
        named.append(text if not traits else text[:-1] + "; shows " + ", ".join(traits) + ")")
    return ("REFERENCE ROLES — the attached references are typed: " + "; ".join(named) +
            ". Never copy a reference's brand, palette, people, copy, signatures or dates.")


def block(stage: str, resolved: dict, typed_refs: list | None = None) -> str:
    """The COMPOSITION CONTRACT for one section at one stage ('' when the
    section has no slots and no backdrop)."""
    entries = [e for e in resolved.get("slots") or []]
    if not entries:
        return ""
    wire = stage in WIREFRAME_STAGES
    lines = ["COMPOSITION CONTRACT — section role "
             f"{resolved.get('role') or 'unclassified'}. Compose each image slot with its declared "
             "treatment; a photo column beside a text column is only one of the allowed treatments."]
    needs_negative = False
    for entry in entries:
        slot, tid = entry["slot"], entry["treatment"]
        t = treatments()[tid]
        words = zone_words(slot, tid)
        if wire:
            text = _fill(t["wireframe_drawing"], words)
            label = _label(slot, tid) if slot.get("slot_id") else "section backdrop"
            lines.append(f"SLOT {label}: {text} Print the slot label with its pixel size, ratio and "
                         f"treatment ({tid}).")
        else:
            text = _fill(t["section_prompt"], words)
            lines.append(f"SLOT {slot.get('slot_id') or 'section backdrop'} (treatment {tid}): {text}")
            if slot.get("mobile_role") and stage == "final-mockups":
                lines.append(f"Mobile role: {slot['mobile_role']}")
        # words over the photo, behind it or overlapping it: never an image column
        # beside a text column. Masks and plain splits keep a column by design.
        needs_negative = needs_negative or t["text_relation"] in ("over", "overlap-card", "behind")
    if needs_negative:
        lines.append(library()["universal_section_negative"])
    if wire:
        lines.append(library()["wireframe_annotations_allowed"])
    ref_text = typed_reference_text(typed_refs or [], {e["treatment"] for e in entries})
    if ref_text:
        lines.append(ref_text)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# typed references from the hosted catalog
# --------------------------------------------------------------------------
def _section_token(section_id) -> str:
    return re.sub(r"^(s|section)\s*0*", "", str(section_id or "").strip().lower())


def _row_has_section(row: dict, token: str) -> bool:
    for entry in row.get("sections") or []:
        lead = re.sub(r"\s.*$", "", str(entry).strip().lower())
        if lead == token:
            return True
    return False


def typed_references(stage: str, platform: str, section_id, treatment_ids_for_section: list,
                     catalog: dict | None = None) -> list:
    """Up to three hosted reference rows for one job, by type: the structural
    sheet that matches the stage and section (wireframe for wireframe stages,
    mockup for mockup stages), then one real example per non-split treatment.
    Rows tagged counter-example-composition are skipped when the section's
    treatment is not split: they teach the split default. Rows flagged
    contains_reference_only_text are never picked."""
    # a row holding placeholder copy, a signature or a person's name is never sent
    rows = [r for r in (catalog or load_catalog()).get("rows") or []
            if r.get("url") and not r.get("contains_reference_only_text")]
    if not rows:
        return []
    token = _section_token(section_id)
    non_split = [t for t in treatment_ids_for_section if t != "split"]
    wanted = ("wireframe", "hybrid-image-map") if stage in WIREFRAME_STAGES else ("mockup",)
    picks = []

    def usable(row):
        return not (non_split and "counter-example-composition" in (row.get("tags") or []))

    for viewport in (platform, "desktop"):
        fits = [r for r in rows
                if r.get("type") in wanted and viewport in str(r.get("viewport") or "").split("+")
                and usable(r) and r.get("form") in ("long-form", "standard")
                and _row_has_section(r, token)]
        fits.sort(key=lambda r: r.get("viewport") != viewport)  # an exact viewport beats a shared sheet
        if fits:
            picks.append(fits[0])
            break
    for tid in non_split:
        for kind in ("mockup-crop", "mockup", "hybrid-image-map"):
            row = next((r for r in rows if r.get("type") == kind and tid in (r.get("traits") or [])
                        and usable(r) and r not in picks), None)
            if row:
                picks.append(row)
                break
    return picks[:MAX_TYPED_REFERENCES]


# --------------------------------------------------------------------------
# budget (B3)
# --------------------------------------------------------------------------
def _plan_slot_treatment(section: dict) -> list:
    """Declared treatments of a wireframe section-plan entry, one per slot;
    an undeclared slot counts as split (the AI default)."""
    out = []
    labels = {}
    slots = section.get("image_slots")
    if isinstance(slots, list):
        for slot in slots:
            if isinstance(slot, dict):
                labels[str(slot.get("slot_id") or slot.get("id"))] = slot
    maps = section.get("slot_labels")
    if isinstance(maps, dict):
        for sid, label in maps.items():
            if isinstance(label, dict):
                labels.setdefault(str(sid), label)
    ids = [str(s) for s in section.get("image_slot_ids") or [] if isinstance(s, str)]
    for sid in ids or list(labels):
        t = (labels.get(sid) or {}).get("treatment")
        out.append(t if t else "split")
    return out


def plan_sections(plan: list) -> list:
    """[(section_id, [treatments], photo_bearing)] from section-plan.json."""
    rows = []
    for section in plan:
        if not isinstance(section, dict):
            continue
        ts = _plan_slot_treatment(section)
        section_level = section.get("treatment")
        if not ts and section_level:
            rows.append((section.get("section_id"), [section_level], False))
        else:
            rows.append((section.get("section_id"), ts, bool(ts)))
    return rows


def budget_failures(rows: list, cues: dict | None = None) -> list:
    """Named COMPOSITION failures for [(section_id, [treatments], photo_bearing)].
    Unknown treatment ids always fail, and so does a treatment the brand's
    composition_cues forbid; the budget itself applies from
    budget.applies_from_photo_sections photo-bearing sections, and a minimum
    that only forbidden treatments could meet is waived."""
    cfg = library()["budget"]
    forbidden = set((cues or {}).get("forbidden") or [])
    failures = []
    for sid, ts, _photo in rows:
        for t in ts:
            if t not in treatments():
                failures.append(f"COMPOSITION: section {sid!r}: unknown treatment {t!r}; allowed: "
                                + ", ".join(treatment_ids()))
            elif t in forbidden:
                failures.append(f"COMPOSITION: section {sid!r}: treatment {t!r} is forbidden by the brand's "
                                "composition_cues")
    photo = [(sid, ts) for sid, ts, p in rows if p]
    if len(photo) < cfg["applies_from_photo_sections"]:
        return failures
    n = len(photo)
    all_split = [sid for sid, ts in photo if all(t == "split" for t in ts)]
    share = len(all_split) / n
    if share > cfg["split_max_share"]:
        failures.append(f"COMPOSITION: {len(all_split)} of {n} photo-bearing sections are split "
                        f"({share:.0%} over the {cfg['split_max_share']:.0%} max); "
                        "declare a words-over-image, band, shaped-crop or intersecting treatment")
    flat = [t for _sid, ts, _p in rows for t in ts]

    def count(flag):
        return sum(1 for t in flat if flag in counts_as(t))

    def possible(flag):
        return any(flag in counts_as(t) for t in treatments() if t not in forbidden)

    if possible("hero-overlay") and count("hero-overlay") < cfg["min_words_over_image_hero"]:
        failures.append("COMPOSITION: no words-over-image hero (overlay-light or overlay-dark-scrim)")
    if possible("band") and count("band") < cfg["min_full_width_bands"]:
        failures.append("COMPOSITION: no full-width band (band-over-texture or band-light-field)")
    if possible("mask") and count("mask") < cfg["min_shaped_crops"]:
        failures.append(f"COMPOSITION: {count('mask')} shaped crops, need at least "
                        f"{cfg['min_shaped_crops']} (mask-circle, mask-arch, mask-pill, mask-diagonal)")
    if possible("circle") and count("circle") < cfg["min_circle_crops"]:
        failures.append("COMPOSITION: no mask-circle crop")
    if possible("intersect") and count("intersect") < cfg["min_intersecting"]:
        failures.append("COMPOSITION: no intersecting treatment (card-overlaps-photo, "
                        "break-the-frame or section-intersect)")
    if cfg.get("no_adjacent_repeat_of_non_split"):
        prev_sid, prev = None, None
        for sid, ts, _p in rows:
            primary = next((t for t in ts if t != "split"), None)
            if primary and primary == prev:
                failures.append(f"COMPOSITION: sections {prev_sid!r} and {sid!r} both use {primary!r}; "
                                "no two adjacent sections share the same non-split treatment")
            prev_sid, prev = sid, primary
    return failures


# --------------------------------------------------------------------------
# QC (B6): pure geometry
# --------------------------------------------------------------------------
def _area(r):
    return max(0.0, r["right"] - r["left"]) * max(0.0, r["bottom"] - r["top"])


def _inter(a, b):
    w = min(a["right"], b["right"]) - max(a["left"], b["left"])
    h = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
    return max(0.0, w) * max(0.0, h)


def _vertical_overlap(a, b):
    h = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
    small = min(a["bottom"] - a["top"], b["bottom"] - b["top"])
    return max(0.0, h) / small if small > 0 else 0.0


def classify_section(section: dict) -> str:
    """OVERLAY, SPLIT or STACK from LAYOUT_JS section data (Q1)."""
    cfg = library()["thresholds"]
    heads = [h for h in section.get("headRects") or [] if _area(h) > 0]
    media = [i["rect"] for i in section.get("images") or []] + [b for b in section.get("bgImages") or []]
    media = [m for m in media if _area(m) > 0]
    if not heads or not media:
        return "STACK"
    head = heads[0]
    covered = min(_area(head), sum(_inter(head, m) for m in media))
    if covered / _area(head) >= cfg["overlay_headline_overlap_min"]:
        return "OVERLAY"
    for m in media:
        disjoint = m["right"] <= head["left"] + 1 or head["right"] <= m["left"] + 1
        if disjoint and _vertical_overlap(m, head) >= cfg["split_vertical_share_min"]:
            return "SPLIT"
    return "STACK"


def radii_class(img: dict) -> str | None:
    """The shape an image's computed radii and clip-path make (Q3, geometric half)."""
    w, h = img["rect"]["width"], img["rect"]["height"]
    if w <= 0 or h <= 0:
        return None
    if img.get("clipPath") and img["clipPath"] != "none":
        return "mask-diagonal"
    tl, tr, br, bl = (img.get("radii") or [0, 0, 0, 0])
    half = min(w, h) / 2 * (library()["thresholds"]["radius_circle_min_pct"] / 50)
    if min(tl, tr, br, bl) >= half - 0.5:
        return "mask-circle" if abs(w - h) / max(w, h) <= 0.03 else "mask-pill"
    if min(tl, tr) >= half - 0.5 and max(br, bl) <= 1:
        return "mask-arch"
    return None


def page_rows(layout_data: dict) -> list:
    """Budget rows from a built page: the declared data-treatment when present,
    else what the geometry shows. Returns (rows, mismatches)."""
    rows, mismatches = [], []
    for idx, section in enumerate(layout_data.get("sections") or []):
        sid = section.get("id") or str(idx + 1)
        measured = classify_section(section)
        declared = [i.get("treatment") for i in section.get("images") or [] if i.get("treatment")]
        if section.get("treatment") and section["treatment"] not in declared:
            declared.append(section["treatment"])   # one count per slot: a section tag repeating its images' tag adds none
        ts = list(declared)
        for img in section.get("images") or []:
            if not img.get("treatment"):
                shape = radii_class(img)
                if shape:
                    ts.append(shape)
        if not ts:
            ts = ["overlay-light"] if measured == "OVERLAY" else (["split"] if section.get("images") or section.get("bgImages") else [])
        for t in declared:
            want = EXPECT_CLASS.get(t)
            if want and measured != want and not (want == "SPLIT" and measured == "STACK"):
                mismatches.append(f"COMPOSITION: section {sid!r} declares {t!r} but the page measures {measured}")
        for img in section.get("images") or []:
            t = img.get("treatment")
            if t and t.startswith("mask-"):
                shape = radii_class(img)
                if shape is None or (t != shape and not (t == "mask-pill" and shape == "mask-circle")):
                    mismatches.append(f"COMPOSITION: section {sid!r} slot {img.get('slot')!r} declares {t!r} "
                                      f"but its computed radius and clip-path make {shape or 'a rectangle'}")
        photo = bool(section.get("images") or section.get("bgImages") or ts)
        rows.append((sid, ts, photo))
    return rows, mismatches


def page_failures(layout_data: dict, cues: dict | None = None) -> list:
    rows, mismatches = page_rows(layout_data)
    return mismatches + budget_failures(rows, cues)


def face_zone_overlap(text_box: dict, frame_box: dict, subject_zone) -> bool:
    """True when the text box intersects the subject zone (percent of the frame) (Q6)."""
    if not subject_zone or len(subject_zone) != 4:
        return False
    w, h = frame_box["right"] - frame_box["left"], frame_box["bottom"] - frame_box["top"]
    zone = {"left": frame_box["left"] + w * subject_zone[0] / 100,
            "right": frame_box["left"] + w * subject_zone[2] / 100,
            "top": frame_box["top"] + h * subject_zone[1] / 100,
            "bottom": frame_box["top"] + h * subject_zone[3] / 100}
    return _inter(text_box, zone) > 0


def safe_margin_ok(text_box: dict, frame_box: dict) -> bool:
    """Overlaid text keeps the safe margin from the frame edge (legibility rule 2)."""
    w, h = frame_box["right"] - frame_box["left"], frame_box["bottom"] - frame_box["top"]
    pct = library()["thresholds"]["safe_margin_min_pct"] / 100
    return (text_box["left"] - frame_box["left"] >= w * pct - 0.5
            and frame_box["right"] - text_box["right"] >= w * pct - 0.5
            and text_box["top"] - frame_box["top"] >= h * pct - 0.5
            and frame_box["bottom"] - text_box["bottom"] >= h * pct - 0.5)


# --------------------------------------------------------------------------
# QC (B6): pixels
# --------------------------------------------------------------------------
def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    r, g, b = rgb[:3]
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _lab(rgb):
    r, g, b = (_lin(c) for c in rgb[:3])
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))


def delta_e(a, b) -> float:
    return math.dist(_lab(a), _lab(b))


def _patch_mean(img, x, y, size):
    box = img.crop((x, y, x + size, y + size)).convert("RGB")
    px = list(box.getdata())
    return tuple(sum(p[i] for p in px) / len(px) for i in range(3))


def corner_test(img, background_rgb, shape: str) -> tuple:
    """Q3 pixel half. `img` is the rendered img box. Corners must match the
    section background (delta E under 3) and the center must differ.
    shape: 'circle' and 'pill' check all four corners, 'arch' the top two.
    Returns (ok, detail)."""
    cfg = library()["thresholds"]
    size = cfg["corner_patch_px"]
    w, h = img.size
    if w < size * 3 or h < size * 3:
        return False, "image box too small to test"
    corners = {"tl": (0, 0), "tr": (w - size, 0), "br": (w - size, h - size), "bl": (0, h - size)}
    if shape == "arch":
        corners = {k: v for k, v in corners.items() if k in ("tl", "tr")}
    bad = {k: round(delta_e(_patch_mean(img, x, y, size), background_rgb), 1)
           for k, (x, y) in corners.items()
           if delta_e(_patch_mean(img, x, y, size), background_rgb) >= cfg["corner_delta_e_max"]}
    center = delta_e(_patch_mean(img, w // 2 - size // 2, h // 2 - size // 2, size), background_rgb)
    if bad:
        return False, f"corner patches differ from the section background (delta E {bad})"
    if center < cfg["center_delta_e_min"]:
        return False, "center patch matches the background: nothing is shown"
    return True, "corners match the background and the center differs"


def light_field_check(img, surface_rgb=None) -> tuple:
    """Q4: the zone behind the type (text and foreground hidden) is within the
    field-to-surface contrast limit of the brand surface AND textured (std at
    least 1.5). The ratio form is palette independent: it holds for a white, a
    beige or a near-black surface alike. Without a surface color the check falls
    back to the absolute luminance floor, which is only right for a near-white
    page."""
    cfg = library()["thresholds"]
    gray = list(img.convert("L").getdata())
    mean = sum(gray) / len(gray)
    std = math.sqrt(sum((v - mean) ** 2 for v in gray) / len(gray))
    low = min(gray)
    if surface_rgb is None:
        if low < cfg["light_field_min_luminance"]:
            return False, f"field minimum luminance {low} is under {cfg['light_field_min_luminance']}"
    else:
        rgb = img.convert("RGB")
        worst = max(contrast_ratio(p, surface_rgb) for p in set(rgb.getdata()))
        if worst > cfg["field_to_surface_max_ratio"]:
            return False, f"field-to-surface contrast {worst:.2f} is over {cfg['field_to_surface_max_ratio']}"
    if std < cfg["light_field_min_std"]:
        return False, f"luminance standard deviation {std:.2f} is under {cfg['light_field_min_std']}: a flat fill, not a texture"
    return True, f"field min {low}, std {std:.2f}"


def backdrop_contrast(img, text_rgb, display: bool) -> tuple:
    """Q2: contrast at the worse of p5 / p95 backdrop luminance against the text
    color. `img` is the backdrop under the text box rendered with text hidden."""
    cfg = library()["thresholds"]
    pixels = list(img.convert("RGB").getdata())
    pixels.sort(key=luminance)
    p5 = pixels[max(0, int(len(pixels) * 0.05) - 1)]
    p95 = pixels[min(len(pixels) - 1, int(len(pixels) * 0.95))]
    ratio = min(contrast_ratio(p5, text_rgb), contrast_ratio(p95, text_rgb))
    need = cfg["contrast_display_min"] if display else cfg["contrast_body_min"]
    return ratio >= need, round(ratio, 2), need


def copy_space_ok(img, copy_zone) -> tuple:
    """Q5 on the raw generated photo: mean gradient inside copy_zone at most
    25 percent of the whole-frame mean."""
    gray = img.convert("L")
    w, h = gray.size
    px = gray.load()

    def grad(x0, y0, x1, y1):
        total, n = 0, 0
        for y in range(y0, max(y0 + 1, y1 - 1)):
            for x in range(x0, max(x0 + 1, x1 - 1)):
                total += abs(px[x + 1, y] - px[x, y]) + abs(px[x, y + 1] - px[x, y])
                n += 1
        return total / max(1, n)

    frame = grad(0, 0, w - 1, h - 1)
    x0, y0, x1, y1 = (int(copy_zone[0] * w / 100), int(copy_zone[1] * h / 100),
                      int(copy_zone[2] * w / 100), int(copy_zone[3] * h / 100))
    zone = grad(min(x0, w - 2), min(y0, h - 2), min(x1, w - 1), min(y1, h - 1))
    limit = library()["thresholds"]["copy_space_gradient_max_ratio"]
    return (zone <= frame * limit, round(zone, 2), round(frame, 2))
