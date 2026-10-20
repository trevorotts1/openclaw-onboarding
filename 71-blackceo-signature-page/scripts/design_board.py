#!/usr/bin/env python3
"""Design Board: the client approves one board per page, built from the page's real images.

Contract: references/design-board.md. One board per page role the funnel has (landing,
product_selection, checkout, upsell_1, upsell_2, downsell_1, thank_you), in the client's own
brand colors, with the client's logo and the page's ACTUAL section images. The stage sits
after the image chain (image-map-upload) and before final-mockups: a board is only ever made
when every image slot already has its generated or supplied file, and the page's images are
re-derived from the run's own artifacts at every check, so an approval cannot outlive a
changed image. final-mockups (and everything after it) does not start without a recorded
client approval of this page's board (`gate`, called by stage_gate.py and stage_executor.py).

Commands:
  design_board.py prompt   <run_dir> [--request FILE]      compose the board prompt, print it
  design_board.py finalize <run_dir> --readback-file TXT [--reader NAME]
                                       record the native-resolution read-back of the board
  design_board.py validate <run_dir> [--require-approval]  QC floor (the stage validator)
  design_board.py approve  <run_dir> --by NAME --evidence REF
                                       record the client's approval (refuses a failing board)
  design_board.py gate     <run_dir>                       approval present and current
Exit codes: 0 pass, 1 named failure, 2 usage.

The read-back is never taken on the caller's word: `finalize` and `validate` read the board
image themselves (tesseract) and refuse a transcript the image does not support.

Brand colors are consumed from scripts/brand_colors.py (resolve / failure); this module never
resolves a palette itself, and fails closed when that resolution is missing or unresolved.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))  # stage_executor / brand_colors live beside this file
import copy_forms  # noqa: E402  the form's page_role names the Design Board's role
import page_kinds  # noqa: E402  SPF030: the landing role's sales / opt-in kind
BOARD_DIR = "design-board"
BOARD_FILE = f"{BOARD_DIR}/design-board.png"
RECORD_FILE = f"{BOARD_DIR}/production-record.json"
DEFAULT_REQUEST = "production-request.json"
BOARD_RATIO = "4:3"
BOARD_PX = (1600, 1200)
MAX_REFERENCES = 14  # the KIE reference transport limit (run-003: 14 references per request)
ALL = "all"
READ_SEP = "\f"  # between the machine reads of one board image (ocr_text)
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
OCR_FLOOR = 0.6        # share of the transcript's words the board image itself must support
ANCHOR_OCR_PERCENT = 70  # share of EACH declared text's words the board image itself must show
PALETTE_MIN_SAMPLES = 12  # pixels (of a 400x300 sample) near each palette color
# Trevor's approved example board belongs to one client (Set for Life): structure reference only.
# Its words, color names and lists never appear on another client's board; the request check
# (copied_example_hits) and the text check (foreign_hits) both read this one record.
EXAMPLE_TERMS = (
    "set for life", "a richer you lives here", "wealth looks good on you",
    "discipline creates freedom", "intentional money a brighter tomorrow",
    "a life of possibilities", "same goals higher standards", "more intentional tomorrows",
    "dream bigger build wealth", "intentional money creates a freer you",
    "editorial financial elegance for grown folks", "official visual direction set for life",
    "soft luxury", "lasting freedom", "fashion forward real people",
    "evergreen #28513f", "champagne #e2c98f", "obsidian #28231f", "terracotta #bc5248")
EXAMPLE_LISTS = {  # a request list that shares >= EXAMPLE_OVERLAP items with one of these is a copy
    "aesthetic_words": ("chic", "elevated", "editorial", "premium", "grown"),
    "icons": ("workbook", "quotes", "presentations", "conversation", "growth", "progress",
              "community", "lifestyle"),
    "cues": ("oversized typography", "strong hierarchy", "spacious layout", "real editorial imagery",
             "couture inspired styling", "one idea per slide", "no clutter",
             "no cartoon money icons", "no corporate template look"),
    "color_names": ("evergreen", "blush", "terracotta", "rose", "gold", "champagne", "ivory",
                    "obsidian")}
EXAMPLE_OVERLAP = {"aesthetic_words": 3, "icons": 4, "cues": 3, "color_names": 4}

ROLE_LABEL = {
    "landing": "landing / sales page", "product_selection": "order (product selection) page",
    "checkout": "checkout page", "upsell_1": "first upsell page", "upsell_2": "second upsell page",
    "downsell_1": "downsell page", "thank_you": "thank-you page"}
ROLE_EMPHASIS = {
    "landing": "full-page persuasion imagery: hero, proof and offer images",
    "product_selection": "package and product imagery, clear and comparable",
    "checkout": "trust, guarantee and product-proof imagery; calm, few images",
    "upsell_1": "the add-on offer's own imagery, close to the main offer's look",
    "upsell_2": "the add-on offer's own imagery, close to the main offer's look",
    "downsell_1": "the lighter offer's own imagery, same brand, softer ask",
    "thank_you": "celebration and next-step imagery"}

# (key, title, required_for)
BLOCKS = (
    ("header", "HEADER", ALL),
    ("side_taglines", "HEADER SIDE TAGLINES", set()),
    ("aesthetic", "BRAND AESTHETIC", {"landing"}),
    ("palette", "OFFICIAL PALETTE", ALL),
    ("gradient", "GRADIENT / ACCENT STRIP", set()),
    ("typography", "TYPOGRAPHY SYSTEM", ALL),
    ("imagery", "IMAGERY DIRECTION", ALL),
    ("icons", "ICON STYLE", {"landing", "product_selection", "thank_you"}),
    ("size", "SIZE GUIDANCE", {"landing"}),
    ("cues", "APPLICATION / DESIGN CUES", ALL),
    ("banner", "HERO / BRAND BANNER STRIP", {"landing"}),
    ("footer", "FOOTER TAGLINES", ALL))
PLACEMENT = {  # where each block sits on the 4:3 sheet; blocks that are absent are skipped
    "header": "full-width top band: logo centered, brand name and positioning line beneath it",
    "aesthetic": "left column under the header: soft rounded chips, one word each",
    "palette": "right column, top: rounded swatches in two rows, each labeled inside or below",
    "side_taglines": "header flanks, left and right of the logo: small spaced-caps taglines",
    "gradient": "right column, directly under the swatches, its caption (if any) centered beneath",
    "typography": "left column, middle: one equal column per type role, sample above usage note",
    "imagery": "left column, lower: the direction line, then the tile grid (the page's images, plus any text or prop tiles listed), tight even gutters",
    "icons": "right column, middle: one row of icons, label under each",
    "size": "right column, lower left: two-column table with thin rules between rows",
    "cues": "right column, lower right: the checklist, one line per cue",
    "banner": "full-width strip below both columns",
    "footer": "thin line at the very bottom, taglines spaced across the width"}
AESTHETIC_WORDS = (5, 6)  # the chips: "five or six words" (references/design-board.md)
TYPE_ROLES = (("display", True), ("serif", False), ("body", True), ("accent", True))


class BoardError(Exception):
    """A named refusal; the message is printed and the command exits 1."""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canon_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def norm(text) -> str:
    return re.sub(r"[^a-z0-9#]+", " ", str(text or "").lower()).strip()


def read_json(path: Path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BoardError(f"cannot read {path}: {exc}")
    if not isinstance(data, dict):
        raise BoardError(f"{path} is not a JSON object")
    return data


# ---------------------------------------------------------------- inputs

def declared_role(run_dir: Path) -> str:
    """The run's page role: intake page_role or launch.page_role, else page-request.json, else
    landing. scripts/page_role.py is the one reader, so the board, the section-count check, the
    wireframe prompt and the gate always agree on the role."""
    sys.path.insert(0, str(HERE))
    try:
        import page_role
    finally:
        sys.path.pop(0)
    return page_role.declared_role(run_dir)


def brand_resolution(run_dir: Path):
    """The resolved client brand (scripts/brand_colors.py contract); fail closed otherwise."""
    sys.path.insert(0, str(HERE))
    try:
        import brand_colors
    except ImportError:
        raise BoardError("brand-color resolution (scripts/brand_colors.py) is not installed; "
                         "the design board cannot start without the client's resolved colors")
    finally:
        sys.path.pop(0)
    res = brand_colors.resolve(run_dir)
    if not res.ok:
        raise BoardError(brand_colors.failure(run_dir) or "brand colors unresolved")
    return res


def palette_entries(res, spec) -> list:
    """The resolved palette as [{role, name, hex}], names from spec.color_names when given."""
    brand = res.brand or {}
    roles = brand.get("palette_roles")
    pairs = []
    for key, val in (roles if isinstance(roles, dict) and roles else res.palette).items():
        vals = val if isinstance(val, list) else [val]
        for i, v in enumerate(vals, 1):
            pairs.append((key if len(vals) == 1 else f"{key}{i}", str(v).upper()))
    names = {str(k).lower(): v for k, v in (spec.get("color_names") or {}).items()}
    out = []
    for role, hexv in pairs:
        name = names.get(role.lower()) or names.get(hexv.lower()) or role.replace("_", " ").title()
        out.append({"role": role, "name": str(name), "hex": hexv})
    return out


def resolve_path(run_dir: Path, raw) -> Path | None:
    if not str(raw or "").strip():
        return None
    p = Path(str(raw))
    for cand in ([p] if p.is_absolute() else [run_dir / p, SKILL_ROOT / p]):
        if cand.is_file():
            return cand
    return None


def load_font_map(run_dir: Path) -> dict:
    fm = read_json(run_dir / "font-action-plan" / "font-map.json")
    fonts = fm.get("fonts")
    if not isinstance(fonts, dict) or not fonts:
        raise BoardError("font-action-plan/font-map.json has no fonts; the board's typography "
                         "comes from it")
    return fm


def find_file(run_dir: Path, raw) -> Path | None:
    """A run image file: run-relative, absolute, or relative to the image map / generation folder."""
    if not str(raw or "").strip():
        return None
    p = Path(str(raw))
    cands = [p] if p.is_absolute() else [run_dir / p, run_dir / "image-map-upload" / p,
                                         run_dir / "image-generation-qc" / p]
    return next((c for c in cands if c.is_file()), None)


def run_rel(run_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(run_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def map_files(run_dir: Path) -> dict:
    """{slot id: file name} from image-map-upload/image-map.json (either dialect)."""
    try:
        data = json.loads((run_dir / "image-map-upload" / "image-map.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for e in (data.get("images") if isinstance(data, dict) else None) or []:
        raw = isinstance(e, dict) and (e.get("asset_file") or e.get("asset_path") or e.get("file")
                                       or e.get("filename"))
        sid = isinstance(e, dict) and (e.get("id") or e.get("master_id"))
        if raw and isinstance(sid, str):
            out[sid] = str(raw)
    return out


def page_images(run_dir: Path, request: dict) -> list:
    """The page's actual images, one item per image slot, each with its file on disk.

    The slot universe is the wireframe's image inventory (the request's slots when a run has
    none). Each file is what the run's own artifacts name for the slot: the image map, the
    generation stage's Image-NNN file, the inventory's supplied file, the request's file, in
    that order (supplied assets: the supplied file first, they are never generated). A slot
    with no file refuses the board: it is never drawn from its art direction."""
    import validate_mockup_slots as vms
    try:
        inv_data = json.loads((run_dir / "desktop-wireframe" / "image-inventory.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        inv_data = None
    inv = {vms.entry_id(e): e for e in vms.inventory_entries(inv_data) if vms.entry_id(e)}
    req = {}
    for sec in request.get("sections") or []:
        for sl in sec.get("slots") or []:
            if sl.get("slot_id"):
                req[str(sl["slot_id"])] = (str(sec.get("section_id")), sl)
    ids = list(inv) or list(req)
    if not ids:
        raise BoardError("the run has no image slots (desktop-wireframe/image-inventory.json or "
                         "the production request's sections); the board needs the page's images")
    plan_sections = vms.plan_slot_sections(run_dir) or {}
    mapped, out, missing = map_files(run_dir), [], []
    for sid in ids:
        entry, (req_section, req_slot) = inv.get(sid) or {}, req.get(sid) or ("", {})
        supplied = vms.is_supplied_entry(entry) or str(req_slot.get("source") or "") == "supplied"
        named = [("inventory", entry.get(k)) for k in ("file", "asset_file", "asset_path")]
        named += [("request", req_slot.get("file"))]
        named = [x for x in named if x[1]]
        if supplied:  # the inventory and the request must agree on a supplied slot's file
            seen = {str(Path(str(r))) for o, r in named}
            if len(seen) > 1:
                raise BoardError(f"slot {sid}: the inventory and the production request name different "
                                 f"supplied files ({', '.join(sorted(seen))}); make them agree, then "
                                 "re-make the board and get it approved again")
        named += [("image-map", mapped.get(sid))] if mapped.get(sid) else []
        if supplied:  # the supplied file leads; a generated map entry never replaces it
            named.sort(key=lambda x: x[0] == "image-map")
        else:
            named.sort(key=lambda x: x[0] != "image-map")
        n = vms.slot_number(sid)
        guesses = [("image-generation-qc", f"image-generation-qc/Image-{n:0{w}d}.png")
                   for w in (3, 2)] if n is not None and not supplied else []
        found = None
        for origin, raw in named:
            found = (origin, find_file(run_dir, raw))
            if found[1] is None:
                raise BoardError(f"slot {sid}: the {origin} names image {raw!r}, which is not on "
                                 "disk; the board shows the page's real images, never a missing one")
            break
        if found is None:
            found = next(((o, find_file(run_dir, r)) for o, r in guesses if find_file(run_dir, r)), None)
        if found is None:
            missing.append(sid)
            continue
        origin, path = found
        out.append({"section_id": str(plan_sections.get(sid) or req_section or "page"),
                    "slot_id": sid, "origin": origin,
                    "source": "supplied" if supplied else str(req_slot.get("source") or "generated"),
                    "file": run_rel(run_dir, path), "sha256": sha256_file(path), "_path": path})
    if missing:
        raise BoardError("the board shows the page's real images, never art-direction stand-ins; "
                         f"no image file yet for slot(s) {', '.join(missing)}. Close "
                         "image-generation-qc and image-map-upload first")
    return out


def extra_tiles(run_dir: Path, spec: dict):
    """Imagery-grid tiles that are not page slots: (supplied prop image items, text tile strings).
    A prop is a supplied image file (hashed into the image set); a text tile is printed text."""
    items, texts = [], []
    for i, tile in enumerate(spec.get("imagery_extras") or [], 1):
        if not isinstance(tile, dict) or bool(tile.get("text")) == bool(tile.get("file")):
            raise BoardError(f"design_board.imagery_extras[{i}] needs exactly one of text or file")
        if tile.get("text"):
            texts.append(str(tile["text"]))
            continue
        path = find_file(run_dir, tile["file"])
        if path is None:
            raise BoardError(f"design_board.imagery_extras[{i}]: file {tile['file']!r} does not exist; "
                             "a prop tile is a supplied image, never drawn")
        items.append({"section_id": "board", "slot_id": f"extra-{i}", "origin": "design_board",
                      "source": "supplied", "file": run_rel(run_dir, path),
                      "sha256": sha256_file(path), "_path": path})
    return items, texts


def image_items(run_dir: Path, request: dict) -> list:
    """Everything the board's image grid shows as a picture: page images, then prop images."""
    return page_images(run_dir, request) + extra_tiles(run_dir, request.get("design_board") or {})[0]


def image_set(items: list) -> dict:
    slots = [{k: s[k] for k in ("section_id", "slot_id", "source", "origin", "file", "sha256")}
             for s in items]
    return {"slots": slots, "sha256": canon_sha(slots)}


# ---------------------------------------------------------------- plan and prompt

def plan(run_dir: Path, request: dict) -> dict:
    spec = request.get("design_board")
    if not isinstance(spec, dict):
        raise BoardError("production request has no design_board block (references/design-board.md)")
    role = spec.get("page_role") or declared_role(run_dir)
    if role not in ROLE_LABEL:
        raise BoardError(f"page_role {role!r} is not one of {sorted(ROLE_LABEL)}")
    if role != declared_role(run_dir) and (run_dir / "intake.json").is_file():
        raise BoardError(f"design_board.page_role {role!r} differs from the run's declared page "
                         f"role {declared_role(run_dir)!r}")
    try:  # SPF030: the landing role is a sales page or an opt-in page; its board says which
        kind = page_kinds.declared(run_dir, request) if role == "landing" else None
    except page_kinds.KindError as exc:
        raise BoardError(str(exc))
    res = brand_resolution(run_dir)
    palette = palette_entries(res, spec)
    stray = sorted(k for k in (spec.get("color_names") or {})
                   if not any(str(k).lower() in (x["role"].lower(), x["hex"].lower()) for x in palette))
    if stray:
        raise BoardError(f"design_board.color_names names colors that are not in the resolved palette "
                         f"({stray}); a name belongs to a palette role or hex, never to a copied example")
    copied = copied_example_hits(spec)
    if copied:
        raise BoardError("design_board copies the example board's content (never another client's): "
                         + "; ".join(copied))
    fonts = load_font_map(run_dir)["fonts"]
    slots = page_images(run_dir, request)
    extra_items, tile_texts = extra_tiles(run_dir, spec)
    logo = resolve_path(run_dir, spec.get("logo")) or resolve_path(
        run_dir, ((res.brand or {}).get("logo") or {}).get("files"))
    missing, blocks = [], []
    typo = spec.get("typography") or {}

    def need(ok, what):
        if not ok:
            missing.append(what)

    for key, title, req_for in BLOCKS:
        required = req_for == ALL or role in req_for
        lines, anchors = [], []
        if key == "header":
            need(str(spec.get("brand_name") or "").strip(), "brand_name")
            need(str(spec.get("positioning_line") or "").strip(), "positioning_line")
            need(logo, "logo (an existing file)")
            if spec.get("brand_name") and spec.get("positioning_line"):
                lines = [f'title line across the top edge printed exactly "{title_line(spec)}"',
                         f'brand name printed exactly "{spec["brand_name"]}"',
                         "the supplied logo reference placed as given, never redrawn or restyled",
                         f'positioning line printed exactly "{spec["positioning_line"]}"']
                anchors = [title_line(spec), spec["brand_name"], spec["positioning_line"]]
        elif key == "side_taglines":
            tags = [str(t) for t in spec.get("side_taglines") or []]
            if tags:
                lines = ["small spaced-caps taglines flanking the logo, printed exactly: "
                         + " | ".join(f'"{t}"' for t in tags)]
                anchors = tags
        elif key == "aesthetic":
            words = [str(w) for w in spec.get("aesthetic_words") or []]
            phrase = str(spec.get("aesthetic_phrase") or "").strip()
            if required:
                need(words, "aesthetic_words")
            if words or phrase:
                need(AESTHETIC_WORDS[0] <= len(words) <= AESTHETIC_WORDS[1],
                     f"aesthetic_words (five or six words, got {len(words)})")
                need(phrase, "aesthetic_phrase (the phrase line under the chips)")
            if words and phrase:
                lines = ["large soft rounded chips, one word each: " + ", ".join(words),
                         f'beneath the chips one phrase line printed exactly "{phrase}"']
                anchors = words + [phrase]
        elif key == "palette":
            lines = [f'swatch labeled exactly "{p["name"]} {p["hex"]}"' for p in palette]
            lines.append("every swatch label in ink chosen for contrast: dark on a light swatch, "
                         "white on a dark one")
            anchors = [p["hex"] for p in palette] + [p["name"] for p in palette]
        elif key == "gradient":
            caption = str(spec.get("gradient_caption") or "").strip()
            if caption and not spec.get("gradient"):
                missing.append("gradient: true (gradient_caption needs the strip)")
            if spec.get("gradient"):
                lines = ["one thin gradient strip blending only the official palette colors"]
                if caption:
                    lines.append(f'its caption printed exactly "{caption}" beneath the strip')
                    anchors = [caption]
        elif key == "typography":
            for trole, trequired in TYPE_ROLES:
                entry = typo.get(trole)
                if trole in ("display", "body", "accent"):
                    need(isinstance(entry, dict) and entry.get("sample") and entry.get("usage"),
                         f"typography.{trole} (sample, usage)")
                    need(trole in fonts, f"font-map fonts.{trole}")
                if isinstance(entry, dict) and entry.get("sample") and entry.get("usage"):
                    font = fonts.get(trole) or entry.get("font") or ""
                    lines.append(f'{trole} column set in {font}: sample printed exactly '
                                 f'"{entry["sample"]}", usage note "{entry["usage"]}"')
                    anchors += [entry["sample"], entry["usage"]] + ([font] if font else [])
        elif key == "imagery":
            need(str(spec.get("imagery_line") or "").strip(), "imagery_line")
            if spec.get("imagery_line"):
                lines = [f'one imagery direction line printed exactly "{spec["imagery_line"]}"',
                         f"then a grid of the page's {len(slots)} section images, each one exactly "
                         "as attached (never redrawn, never replaced), cropped only to fit its tile, "
                         "one tile per image, in slot order"]
                anchors = [spec["imagery_line"]]
                if extra_items:
                    lines.append(f"plus {len(extra_items)} supplied prop image(s), attached after the "
                                 "section images, placed among the tiles exactly as given")
                if tile_texts:
                    lines.append("plus text tiles on a plain palette ground, each printed exactly: "
                                 + " | ".join(f'"{t}"' for t in tile_texts))
                    anchors += tile_texts
        elif key == "icons":
            icons = [str(i) for i in spec.get("icons") or []]
            if required:
                need(icons, "icons")
            if icons:
                lines, anchors = ["one row of matching line icons in the official palette, each with "
                                  "its label: " + ", ".join(icons)], icons
        elif key == "size":
            rows = size_rows(load_font_map(run_dir)) if spec.get("size_guidance") or required else []
            if required:
                need(rows, "size guidance rows (font-map typography with px sizes)")
            if rows:
                lines = ["a two-column table, label then size: " + "; ".join(rows)]
                anchors = [r.split(":")[0] for r in rows]
        elif key == "cues":
            cues = [str(c) for c in spec.get("cues") or []]
            need(len(cues) >= 5, "cues (at least five)")
            if cues:
                lines, anchors = ["checklist, each line with a palette-colored check mark: "
                                  + "; ".join(cues)], cues
        elif key == "banner":
            line = str(spec.get("banner_line") or "").strip()
            sub = str(spec.get("banner_subline") or "").strip()
            if required or sub:
                need(line, "banner_line")
            if line:
                lines, anchors = [f'a wide brand banner strip in the palette carrying the line '
                                  f'"{line}" and the logo'], [line]
                if sub:
                    lines.append(f'a second line printed exactly "{sub}" beside the logo')
                    anchors.append(sub)
        elif key == "footer":
            tags = [str(t) for t in spec.get("footer_taglines") or []]
            need(tags, "footer_taglines")
            if tags:
                lines, anchors = ["footer line printed exactly: " + " | ".join(tags)], tags
        blocks.append({"key": key, "title": title, "required": required,
                       "present": bool(lines), "lines": lines, "anchors": anchors})
    if missing:
        raise BoardError("design board content missing (never invented): " + "; ".join(missing))
    return {"role": role, "kind": kind, "spec": spec, "palette": palette, "fonts": fonts, "slots": slots,
            "extra_items": extra_items, "tile_texts": tile_texts,
            "logo": logo, "blocks": blocks, "res": res,
            "expected": {"required_blocks": [b["key"] for b in blocks if b["required"]],
                         "anchors": {b["key"]: b["anchors"] for b in blocks if b["present"]},
                         "hexes": sorted({p["hex"] for p in palette})}}


def size_rows(font_map: dict) -> list:
    rows = []
    for entry in font_map.get("typography") or []:
        sizes = entry.get("sizes") or {}
        d, m = (sizes.get("desktop") or {}).get("px"), (sizes.get("mobile") or {}).get("px")
        if entry.get("element") and d and m:
            rows.append(f"{entry['element']}: {d}px desktop / {m}px mobile")
    return rows


SHEET_FILE = f"{BOARD_DIR}/overflow-sheet.png"


def reference_plan(p: dict, run_dir: Path):
    """(direct image paths, overflow items, overflow sheet path). The transport takes at most
    MAX_REFERENCES attachments: the logo and the images; when the images do not fit, the last
    attachment is one contact sheet of the rest (built from the real files, never drawn)."""
    items = p["slots"] + p["extra_items"]
    if len(items) <= MAX_REFERENCES - 1:
        return [x["_path"] for x in items], [], None
    keep = MAX_REFERENCES - 2
    return [x["_path"] for x in items[:keep]], items[keep:], run_dir / SHEET_FILE


def references(p: dict, run_dir: Path | None = None) -> list:
    direct, overflow, sheet = reference_plan(p, run_dir or Path(p["logo"]).parent)
    return [str(r) for r in [p["logo"], *direct, *([sheet] if overflow else [])]]


def build_overflow_sheet(p: dict, run_dir: Path) -> None:
    """Write the contact sheet of the overflow images (the executor calls this before generating)."""
    from PIL import Image
    _, overflow, sheet = reference_plan(p, run_dir)
    if not overflow:
        return
    cols = int(len(overflow) ** 0.5 + 0.999)
    rows = -(-len(overflow) // cols)
    cell = (480, 360)
    canvas = Image.new("RGB", (cols * cell[0], rows * cell[1]), (255, 255, 255))
    for i, item in enumerate(overflow):
        with Image.open(item["_path"]) as im:
            im = im.convert("RGB")
            im.thumbnail(cell)
            canvas.paste(im, ((i % cols) * cell[0] + (cell[0] - im.width) // 2,
                              (i // cols) * cell[1] + (cell[1] - im.height) // 2))
    sheet.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(sheet)


def compose_prompt(p: dict, request: dict, run_dir: Path | None = None):
    """(prompt, sizes) for one board; sizes follow the executor's budget-band convention."""
    import stage_executor as se
    spec, role = p["spec"], p["role"]
    label, emphasis = (page_kinds.board(p["kind"]) if p.get("kind")
                       else (ROLE_LABEL[role], ROLE_EMPHASIS[role]))
    aesthetic = ", ".join(str(w).lower() for w in spec.get("aesthetic_words") or [])
    out = [f'DESIGN BOARD — one landscape ({BOARD_RATIO}) brand board sheet titled "'
           f'{title_line(spec)}" for the client\'s '
           f'{label}. It is the approval sheet shown before the page is built, made '
           "from the page's real, finished images: "
           + (f"{aesthetic}; " if aesthetic else "")
           + "generous spacing, every text string exactly as given below.",
           f"PAGE ROLE EMPHASIS — {emphasis}."]
    out.append("LAYOUT — 4:3 sheet, even outer margin, two columns under a full-width header, "
               "hairline rules between blocks, generous whitespace; placement: "
               + "; ".join(f'{b["title"].lower()}: {PLACEMENT[b["key"]]}' for b in p["blocks"]
                           if b["present"]) + ".")
    for b in p["blocks"]:
        if b["present"]:
            body = "; ".join(b["lines"])
            out.append(f'BLOCK {b["title"]}' + (" (required)" if b["required"] else "")
                       + " — " + body + ("" if body[-1] in ".!?" else "."))
    out.append("BRAND COLORS — this board uses only the client's official palette: "
               + "; ".join(f'{x["name"]} {x["hex"]}' for x in p["palette"])
               + ". No other chromatic color; neutrals only for photo plates.")
    refs = references(p, run_dir)
    overflow = reference_plan(p, run_dir or Path(p["logo"]).parent)[1]
    note = (f"REFERENCES — {len(refs)} attached: the client logo first, then the page's section "
            "images in slot order (then any supplied prop images); every picture tile is one of "
            "these attachments exactly as given, and no picture is drawn from a description.")
    if overflow:
        note += (f" The last attachment is a contact sheet of the remaining {len(overflow)} images, "
                 "left to right, top to bottom, in slot order; place each as its own tile.")
    out.append(note)
    out.append("NEGATIVE BLOCK — print no brand name, logo, tagline, color or person belonging to "
               "any other client or example; no placeholder text, no lorem, no watermark, no "
               "production labels; no text that is not given above.")
    prompt = se.sanitize_prompt("\n\n".join(out))
    budget = se.prompt_budget(request.get("model"))
    sizes = {"chars": len(prompt), "floor_chars": budget and budget["floor_chars"],
             "target_chars": budget and budget["target_chars"],
             "max_chars": budget and budget["max_chars"]}
    if budget and len(prompt) < budget["floor_chars"]:  # the executor's convention: warn, never pad
        print(f"WARN prompt_budget design-board: {len(prompt)} chars, "
              f"{budget['floor_chars'] - len(prompt)} below the {budget['floor_chars']}-char floor; "
              "add genuine board specification, never filler", file=sys.stderr)
    if budget and len(prompt) > budget["max_chars"]:
        raise BoardError(f"design board prompt is {len(prompt)} chars, over the "
                         f"{budget['max_chars']}-char model maximum; shorten board content")
    foreign = foreign_hits(prompt, spec)
    if foreign:
        raise BoardError("design board prompt names another client's brand: " + ", ".join(foreign))
    return prompt, sizes


def title_line(spec: dict) -> str:
    """The sheet's own title, printed across the top edge (the prompt's first sentence)."""
    return f'{spec["brand_name"]} — OFFICIAL VISUAL DIRECTION'


def is_example_client(spec: dict) -> bool:
    return EXAMPLE_TERMS[0] in norm(spec.get("brand_name"))


def copied_example_hits(spec: dict) -> list:
    """Request lists lifted from the example board: one named line per list that shares enough
    items with the example's list (a client whose own brand is the example may use them)."""
    if is_example_client(spec):
        return []
    hits = []
    for key, example in EXAMPLE_LISTS.items():
        raw = spec.get(key) or []
        vals = raw.values() if isinstance(raw, dict) else raw
        shared = sorted({norm(v) for v in vals} & set(example))
        if len(shared) >= EXAMPLE_OVERLAP[key]:
            hits.append(f"{key} shares {len(shared)} items with the example board ({', '.join(shared)})")
    return hits


def foreign_hits(text: str, spec: dict) -> list:
    """Another client's brand text in `text`: the other clients' names (derived from the
    visual-standards manifest) and the example board's words. A name the run's own brand name
    contains is the client's own; a client named like the example may use its words."""
    import stage_executor as se
    own = norm(spec.get("brand_name"))
    terms = {norm(n) for n in se.cross_client_names()}
    if not is_example_client(spec):
        terms |= set(EXAMPLE_TERMS)
    body = norm(text)
    return sorted(t for t in terms if t and re.search(rf"\b{re.escape(t)}\b", body)
                  and not re.search(rf"\b{re.escape(t)}\b", own))


# ---------------------------------------------------------------- record

def write_record(run_dir: Path, p: dict, prompt: str, result: dict, revision: int):
    board = run_dir / BOARD_FILE
    iset = image_set(p["slots"] + p["extra_items"])
    record = {
        "artifact": "design-board", "page_role": p["role"], "page_kind": p.get("kind"),
        "revision": revision,
        "brand": {"name": p["spec"]["brand_name"], "positioning_line": p["spec"]["positioning_line"],
                  "logo": {"file": str(p["logo"]), "sha256": sha256_file(p["logo"])}},
        "palette": p["palette"], "palette_sha256": canon_sha(p["palette"]),
        "palette_source": str(p["res"].source),
        "typography": {r: {"font": p["fonts"].get(r), **(p["spec"]["typography"].get(r) or {})}
                       for r, _ in TYPE_ROLES if (p["spec"]["typography"] or {}).get(r)},
        "image_set": iset,
        "reference_overflow": [x["slot_id"] for x in reference_plan(p, run_dir)[1]],
        "expected": p["expected"],
        "board": {"file": BOARD_FILE, "sha256": sha256_file(board), "ratio": BOARD_RATIO},
        "generation": {"provider": result.get("provider"), "mode": result.get("mode"),
                       "model": result.get("model"), "task_id": result.get("task_id"),
                       "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
                       "references": references(p, run_dir), "generated_at": now_iso()},
        "readback": None, "approval": None,
        "note": "this record is not a gate receipt; approval is the client's, recorded by "
                "design_board.py approve",
    }
    save_record(run_dir, record)
    return record


def save_record(run_dir: Path, record: dict):
    path = run_dir / RECORD_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_record(run_dir: Path) -> dict:
    return read_json(run_dir / RECORD_FILE)


def approval_binding(record: dict) -> dict:
    return {"board_sha256": record["board"]["sha256"], "image_set_sha256": record["image_set"]["sha256"],
            "palette_sha256": record["palette_sha256"], "page_role": record["page_role"]}


# ---------------------------------------------------------------- validate

def validate(run_dir: Path, require_approval=False, request_name=DEFAULT_REQUEST) -> list:
    """The QC floor. Returns one named failure string per problem; empty means pass."""
    if not (run_dir / RECORD_FILE).is_file():
        return [f"design board: no board yet, {RECORD_FILE} does not exist"]
    try:
        rec = load_record(run_dir)
    except BoardError as exc:
        return [f"design board: no usable production record ({exc})"]
    fails = []
    if rec.get("artifact") != "design-board":
        fails.append("design board: record artifact must be 'design-board'")
    role = rec.get("page_role")
    if role not in ROLE_LABEL:
        fails.append(f"design board: page_role {role!r} is not a page role")
    elif (run_dir / "intake.json").is_file() and role != declared_role(run_dir):
        fails.append(f"design board: board is for {role!r}, the run declares {declared_role(run_dir)!r}")
    if role == "landing" and (run_dir / "intake.json").is_file():
        try:
            want_kind = page_kinds.declared(run_dir, {})
        except page_kinds.KindError as exc:
            want_kind = None
            fails.append(f"design board: {exc}")
        if want_kind != rec.get("page_kind"):
            fails.append(f"design board: board is for page kind {rec.get('page_kind')!r}, "
                         f"the run declares {want_kind!r}")
    try:
        board_png = run_dir / BOARD_FILE
        if not board_png.is_file():
            fails.append(f"design board: {BOARD_FILE} is missing")
        elif sha256_file(board_png) != (rec.get("board") or {}).get("sha256"):
            fails.append("design board: the board image changed after it was recorded")
    except (OSError, TypeError):
        fails.append("design board: board file unreadable")
    gen = rec.get("generation") or {}
    if gen.get("provider") in (None, "stub"):
        fails.append("design board: a stub placeholder is not a board; generate it with the real "
                     "provider (or place the client-supplied board)")
    # palette = the resolved client palette
    try:
        res = brand_resolution(run_dir)
        spec = {}
        try:
            spec = (read_json(run_dir / request_name).get("design_board") or {})
        except BoardError:
            pass
        want = palette_entries(res, spec)
        got = rec.get("palette")
        if [(x["role"], x["hex"]) for x in want] != [(x.get("role"), x.get("hex")) for x in got or []]:
            fails.append("design board: palette is not the client's resolved palette "
                         f"(resolved {[x['hex'] for x in want]}, board {[x.get('hex') for x in got or []]})")
        if rec.get("palette_sha256") != canon_sha(got):
            fails.append("design board: palette hash does not match the recorded palette")
    except BoardError as exc:
        fails.append(f"design board: {exc}")
    # logo
    logo = (rec.get("brand") or {}).get("logo") or {}
    lp = resolve_path(run_dir, logo.get("file"))
    if lp is None:
        fails.append("design board: the client logo file is missing")
    elif sha256_file(lp) != logo.get("sha256"):
        fails.append("design board: the logo file changed after the board was made")
    # images = the page's actual section images
    fails += image_set_failures(run_dir, rec, request_name)
    # required blocks and text fidelity from the native-resolution read-back
    fails += readback_failures(run_dir, rec)
    if require_approval:
        fails += approval_failures(rec)
    return fails


def image_set_failures(run_dir, rec, request_name) -> list:
    """The page's images, re-derived from the run's own artifacts now, must equal the recorded
    set: same slots, same files, same bytes. A slot that gains or changes a file, a replaced
    supplied image, an added or removed slot all make the board (and its approval) stale."""
    fails, recorded = [], (rec.get("image_set") or {}).get("slots") or []
    if (rec.get("image_set") or {}).get("sha256") != canon_sha(recorded):
        fails.append("design board: image set hash does not match the recorded slots")
    try:
        request = read_json(run_dir / request_name)
    except BoardError:
        request = {}
    try:
        now = image_set(image_items(run_dir, request))["slots"]
    except BoardError as exc:
        return fails + [f"design board: the page's images cannot be re-derived from the run ({exc})"]
    key = lambda s: (s.get("section_id"), s.get("slot_id"))  # noqa: E731
    was, cur = {key(s): s for s in recorded}, {key(s): s for s in now}
    added, removed = sorted(set(cur) - set(was)), sorted(set(was) - set(cur))
    changed = sorted(k[1] for k in set(cur) & set(was) if cur[k] != was[k])
    if added or removed or changed:
        fails.append("design board: the page's images changed since the board "
                     f"(added {added}, removed {removed}, " + ", ".join(f"{c} changed" for c in changed)
                     + "); re-make the board and get it approved again")
    return fails


def tokens(text) -> list:
    return sorted({w for w in norm(text).split() if len(w) >= 3})


def support(words, ocr_words) -> float:
    """Share of `words` the OCR words contain, exactly or within one misread character."""
    if not words:
        return 1.0
    seen = set(ocr_words)
    hit = sum(w in seen or bool(difflib.get_close_matches(w, seen, n=1, cutoff=0.8)) for w in words)
    return hit / len(words)


def token_list(text) -> list:
    return [w for w in norm(text).split() if len(w) >= 3]


def within_one(a: str, b: str) -> bool:
    """One misread character: a substitution, a dropped or an added character."""
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] or a[i:] == b[i + 1:] or a[i + 1:] == b[i:]


def image_misses(anchors_by_block: dict, ocr: str) -> dict:
    """{block: declared texts the board image does not show}, judged per text.

    Every word of every declared text must be a word the machine read of the image has, and a
    machine-read word is used up by the text it matches (a word printed once cannot show two
    texts). A word matches exactly, or, when it has five or more characters, within one misread
    character; a short word never matches a different word that merely looks like it (grow is
    not growth). A text counts as shown when ANCHOR_OCR_PERCENT of its words are matched, so one
    missing tagline, caption, tile or cue of a block fails that block by name."""
    pool = {}  # a word's count is its largest count in any one machine read, never the sum
    for one_read in ocr.split(READ_SEP):
        seen = {}
        for w in token_list(one_read):
            seen[w] = seen.get(w, 0) + 1
        for w, n in seen.items():
            pool[w] = max(pool.get(w, 0), n)
    need = [(b, i, w) for b, anchors in sorted(anchors_by_block.items())
            for i, a in enumerate(anchors) for w in token_list(a)]
    hit = set()
    for n, (_b, _i, w) in enumerate(need):  # exact matches first, so a near miss never steals one
        if pool.get(w):
            pool[w] -= 1
            hit.add(n)
    for n, (_b, _i, w) in enumerate(need):
        if n in hit or len(w) < 5:
            continue
        near = next((k for k in sorted(pool) if pool[k] and within_one(w, k)), None)
        if near:
            pool[near] -= 1
            hit.add(n)
    out = {}
    for b, anchors in sorted(anchors_by_block.items()):
        for i, a in enumerate(anchors):
            ids = [n for n, (nb, ni, _w) in enumerate(need) if (nb, ni) == (b, i)]
            if ids and sum(n in hit for n in ids) < -(-len(ids) * ANCHOR_OCR_PERCENT // 100):
                out.setdefault(b, []).append(a)
    return out


def ocr_text(png: Path) -> str:
    """The board image read by a machine, independent of whatever transcript the caller has.
    Two reads, separated by a form feed: the image as is, and its inverted grayscale (light
    text on a dark or colored ground is read far better inverted)."""
    exe = shutil.which("tesseract")
    if not exe:
        raise BoardError("tesseract, the board's independent text reader, is not installed "
                         "(brew install tesseract / apt install tesseract-ocr); the read-back "
                         "cannot be checked against the image without it")

    def read(path: Path) -> str:
        out = subprocess.run([exe, str(path), "stdout", "--psm", "11"], text=True,
                             capture_output=True, timeout=180)
        if out.returncode != 0:
            raise BoardError(f"tesseract failed on {png.name}: {out.stderr.strip()[:200]}")
        return out.stdout

    reads = [read(png)]
    try:
        from PIL import Image, ImageOps
        with tempfile.TemporaryDirectory(prefix="board-ocr-") as td:
            inverted = Path(td) / "inverted.png"
            with Image.open(png) as im:
                ImageOps.invert(ImageOps.grayscale(im.convert("RGB"))).save(inverted)
            reads.append(read(inverted))
    except ImportError:
        pass
    return READ_SEP.join(reads)


def palette_pixel_failures(board: Path, palette: list) -> list:
    """Each palette color is actually present in the board's pixels (a flat or off-brand image
    cannot pass on text alone)."""
    try:
        from PIL import Image
    except ImportError:
        return ["design board: Pillow is not installed; the palette cannot be measured on the board"]
    with Image.open(board) as im:
        im = im.convert("RGB").resize((400, 300), Image.NEAREST)
    counts = {}
    for px in im.getdata():
        counts[px] = counts.get(px, 0) + 1
    absent = []
    for x in palette:
        target = tuple(int(x["hex"][i:i + 2], 16) for i in (1, 3, 5))
        near = sum(n for px, n in counts.items()
                   if sum((a - b) ** 2 for a, b in zip(px, target)) <= 40 ** 2)
        if near < PALETTE_MIN_SAMPLES:
            absent.append(x["hex"])
    return [f"design board: palette colors absent from the board's pixels: {absent}"] if absent else []


def readback_failures(run_dir: Path, rec) -> list:
    """The read-back is checked against the board image itself: a machine read (OCR) of the board
    must support the transcript overall and every block of it. A transcript the image does not
    support, or one recorded for another board file, fails."""
    rb = rec.get("readback")
    if not isinstance(rb, dict) or not str(rb.get("text") or "").strip() or not rb.get("native_resolution"):
        return ["design board: no native-resolution read-back recorded (design_board.py finalize)"]
    fails = []
    if rb.get("board_sha256") != (rec.get("board") or {}).get("sha256"):
        fails.append("design board: the read-back was taken from a different board image; read it again")
    board = run_dir / BOARD_FILE
    if not board.is_file():
        return fails  # the missing board is reported by validate
    try:
        ocr = ocr_text(board)
    except BoardError as exc:
        return fails + [f"design board: {exc}"]
    text, ocr_words = norm(rb["text"]), tokens(ocr)
    overall = support(tokens(rb["text"]), ocr_words)
    if overall < OCR_FLOOR:
        fails.append(f"design board: the read-back is not supported by the board image "
                     f"(the image shows {overall:.0%} of its words, {OCR_FLOOR:.0%} needed)")
    exp = rec.get("expected") or {}
    anchors_by_block = exp.get("anchors") or {}
    for block in exp.get("required_blocks") or []:
        if not anchors_by_block.get(block):
            fails.append(f"design board: required block {block!r} has no content recorded")
    for block, anchors in anchors_by_block.items():  # every block on the board, required or not
        absent = [a for a in anchors if norm(a) not in text]
        if absent:
            fails.append(f"design board: block {block!r} is not legible on the board "
                         f"(read-back lacks {absent[:4]})")
    for block, unseen in image_misses(anchors_by_block, ocr).items():  # the image itself, per text
        fails.append(f"design board: block {block!r} is not on the board image "
                     f"(the image does not show {unseen[:4]})")
    want = set(exp.get("hexes") or [])
    found = {h.upper() for h in HEX.findall(rb["text"])}
    on_image = {h.upper() for h in HEX.findall(ocr)}
    stray = {h for h in on_image - want if not difflib.get_close_matches(h, want, n=1, cutoff=0.8)}
    if (found - want) or stray:
        fails.append("design board: board prints colors outside the client palette: "
                     f"{sorted((found - want) | stray)}")
    if want - found:
        fails.append(f"design board: palette colors not printed on the board: {sorted(want - found)}")
    fails += palette_pixel_failures(board, rec.get("palette") or [])
    spec_like = {"brand_name": (rec.get("brand") or {}).get("name"),
                 "positioning_line": (rec.get("brand") or {}).get("positioning_line")}
    foreign = foreign_hits(rb["text"] + "\n" + ocr, spec_like)
    if foreign:
        fails.append("design board: board carries another client's brand text: " + ", ".join(foreign))
    return fails


def approval_failures(rec) -> list:
    ap = rec.get("approval")
    if not isinstance(ap, dict):
        return ["design board: no client approval recorded for this page's board "
                "(design_board.py approve); final-mockups and the stages after it may not start"]
    fails = []
    if ap.get("decision") != "approved":
        fails.append("design board: the recorded decision is not 'approved'")
    for key in ("approved_by", "evidence_ref", "approved_at"):
        if not str(ap.get(key) or "").strip():
            fails.append(f"design board: approval lacks {key}")
    try:
        bound = approval_binding(rec)
    except (KeyError, TypeError):
        return fails + ["design board: record cannot be bound to an approval"]
    stale = [k for k, v in bound.items() if ap.get(k) != v]
    if stale:
        fails.append("design board: approval is stale, the board changed after the client approved "
                     f"({', '.join(stale)}); make the approval again")
    return fails


def gate_failures(run_dir: Path, request_name=DEFAULT_REQUEST) -> list:
    return validate(Path(run_dir), require_approval=True, request_name=request_name)


def approve(run_dir: Path, by: str, evidence: str, request_name=DEFAULT_REQUEST) -> dict:
    fails = validate(run_dir, request_name=request_name)
    if fails:
        raise BoardError("a board that fails QC is never approved: " + " | ".join(fails))
    rec = load_record(run_dir)
    rec["approval"] = {"decision": "approved", "party": "client", "approved_by": by,
                       "evidence_ref": evidence, "approved_at": now_iso(), **approval_binding(rec)}
    save_record(run_dir, rec)
    return rec["approval"]


def finalize(run_dir: Path, text: str, reader: str):
    """Record the reader's transcript of the board, after the board image itself supports it."""
    rec = load_record(run_dir)
    board = run_dir / BOARD_FILE
    if not board.is_file() or sha256_file(board) != (rec.get("board") or {}).get("sha256"):
        raise BoardError(f"{BOARD_FILE} is missing or changed since it was recorded; the read-back "
                         "is taken from the board on record")
    ocr = ocr_text(board)
    overall = support(tokens(text), tokens(ocr))
    if overall < OCR_FLOOR:
        raise BoardError(f"the read-back is not supported by the board image (the image shows "
                         f"{overall:.0%} of its words, {OCR_FLOOR:.0%} needed); read the board "
                         "itself, not the contract")
    rec["readback"] = {"native_resolution": True, "read_by": reader, "text": text,
                       "board_sha256": rec["board"]["sha256"], "ocr_text": ocr,
                       "read_at": now_iso()}
    rec["approval"] = None  # a new read-back means a re-checked board; approval is made after it
    save_record(run_dir, rec)


# ---------------------------------------------------------------- cli

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prompt", "finalize", "validate", "approve", "gate"):
        s = sub.add_parser(name)
        s.add_argument("run_dir", type=Path)
        s.add_argument("--request", default=DEFAULT_REQUEST)
        if name == "finalize":
            s.add_argument("--readback-file", type=Path, required=True)
            s.add_argument("--reader", default="board-reader")
        if name == "validate":
            s.add_argument("--require-approval", action="store_true")
        if name == "approve":
            s.add_argument("--by", required=True)
            s.add_argument("--evidence", required=True)
    a = ap.parse_args(argv)
    run_dir = a.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"FAIL: run dir {run_dir} does not exist")
        return 2
    sys.path.insert(0, str(HERE))
    try:
        if a.cmd == "prompt":
            request = read_json(run_dir / a.request)
            prompt, sizes = compose_prompt(plan(run_dir, request), request, run_dir)
            print(prompt)
            print(f"\n[chars={sizes['chars']} floor={sizes['floor_chars']} max={sizes['max_chars']}]",
                  file=sys.stderr)
            return 0
        if a.cmd == "finalize":
            finalize(run_dir, a.readback_file.read_text(encoding="utf-8"), a.reader)
            print(f"RECORDED read-back in {RECORD_FILE}")
            return 0
        if a.cmd == "approve":
            ap_rec = approve(run_dir, a.by, a.evidence, a.request)
            print(f"APPROVED design board for {load_record(run_dir)['page_role']} by {ap_rec['approved_by']}")
            return 0
        fails = (gate_failures(run_dir, a.request) if a.cmd == "gate"
                 else validate(run_dir, getattr(a, "require_approval", False), a.request))
        if fails:
            print("\n".join(f"FAIL: {f}" for f in fails))
            return 1
        print(f"PASS: design board ({'approved, ' if a.cmd == 'gate' or getattr(a, 'require_approval', False) else ''}"
              "QC floor met)")
        return 0
    except BoardError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
