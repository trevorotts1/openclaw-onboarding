#!/usr/bin/env python3
"""Design Board: the client approves one board per page before any wireframe starts.

Contract: references/design-board.md. One board per page role the funnel has (landing,
product_selection, checkout, upsell_1, upsell_2, downsell_1, thank_you), in the client's own
brand colors, with the client's logo and the page's section images. The stage sits after
font-action-plan and before desktop-wireframe; no wireframe or mockup stage starts without a
recorded client approval of this page's board (`gate`, called by stage_gate.py and by
stage_executor.py).

Commands:
  design_board.py prompt   <run_dir> [--request FILE]      compose the board prompt, print it
  design_board.py finalize <run_dir> --readback-file TXT [--reader NAME]
                                       record the native-resolution read-back of the board
  design_board.py validate <run_dir> [--require-approval]  QC floor (the stage validator)
  design_board.py approve  <run_dir> --by NAME --evidence REF
                                       record the client's approval (refuses a failing board)
  design_board.py gate     <run_dir>                       approval present and current
Exit codes: 0 pass, 1 named failure, 2 usage.

Brand colors are consumed from scripts/brand_colors.py (resolve / failure); this module never
resolves a palette itself, and fails closed when that resolution is missing or unresolved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))  # stage_executor / brand_colors live beside this file
BOARD_DIR = "design-board"
BOARD_FILE = f"{BOARD_DIR}/design-board.png"
RECORD_FILE = f"{BOARD_DIR}/production-record.json"
DEFAULT_REQUEST = "production-request.json"
BOARD_RATIO = "4:3"
BOARD_PX = (1600, 1200)
MAX_REFERENCES = 14  # the KIE reference transport limit (run-003: 14 references per request)
ALL = "all"
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
# Words that belong to the Set for Life example board; never another client's board.
EXAMPLE_TERMS = ("set for life", "a richer you lives here", "wealth looks good on you",
                 "discipline creates freedom", "intentional money a brighter tomorrow")

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
    "gradient": "right column, directly under the swatches",
    "typography": "left column, middle: one equal column per type role, sample above usage note",
    "imagery": "left column, lower: the direction line, then the image tile grid, tight even gutters",
    "icons": "right column, middle: one row of icons, label under each",
    "size": "right column, lower left: two-column table with thin rules between rows",
    "cues": "right column, lower right: the checklist, one line per cue",
    "banner": "full-width strip below both columns",
    "footer": "thin line at the very bottom, taglines spaced across the width"}
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
    """The run's page role: intake launch.page_role, else page-request.json, else landing."""
    for name, key in (("intake.json", "launch"), ("page-request.json", None)):
        try:
            data = json.loads((run_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data = data.get(key) if key and isinstance(data, dict) else data
        if isinstance(data, dict) and isinstance(data.get("page_role"), str) and data["page_role"]:
            return data["page_role"]
    return "landing"


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


def slot_list(run_dir: Path, request: dict) -> list:
    out = []
    for section in request.get("sections") or []:
        for slot in section.get("slots") or []:
            raw = slot.get("file")
            path = resolve_path(run_dir, raw) if raw else None
            if raw and path is None:
                raise BoardError(f"slot {slot.get('slot_id')}: image file {raw!r} does not exist; "
                                 "the board shows the page's real images, never a missing one")
            out.append({"section_id": str(section.get("section_id")),
                        "slot_id": str(slot.get("slot_id") or ""),
                        "art_direction": str(slot.get("art_direction") or ""),
                        "source": str(slot.get("source") or ("supplied" if path else "planned")),
                        "file": str(raw) if path else None,
                        "sha256": sha256_file(path) if path else None,
                        "_path": path})
    if not out:
        raise BoardError("the production request has no image slots; the board needs the page's "
                         "section images")
    return out


def image_set(slots: list) -> dict:
    items = [{k: s[k] for k in ("section_id", "slot_id", "source", "file", "sha256")} for s in slots]
    return {"slots": items, "sha256": canon_sha(items)}


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
    res = brand_resolution(run_dir)
    palette = palette_entries(res, spec)
    fonts = load_font_map(run_dir)["fonts"]
    slots = slot_list(run_dir, request)
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
                lines = [f'brand name printed exactly "{spec["brand_name"]}"',
                         "the supplied logo reference placed as given, never redrawn or restyled",
                         f'positioning line printed exactly "{spec["positioning_line"]}"']
                anchors = [spec["brand_name"], spec["positioning_line"]]
        elif key == "aesthetic":
            words = [str(w) for w in spec.get("aesthetic_words") or []]
            if required:
                need(words, "aesthetic_words")
            if words:
                lines, anchors = ["large soft rounded chips, one word each: " + ", ".join(words)], words
        elif key == "palette":
            lines = [f'swatch labeled exactly "{p["name"]} {p["hex"]}"' for p in palette]
            anchors = [p["hex"] for p in palette] + [p["name"] for p in palette]
        elif key == "gradient":
            if spec.get("gradient"):
                lines = ["one thin gradient strip blending only the official palette colors"]
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
                         f"then a grid of the page's {len(slots)} section images, each shown "
                         "as supplied, cropped only to fit its tile, one tile per slot"]
                anchors = [spec["imagery_line"]]
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
            if required:
                need(line, "banner_line")
            if line:
                lines, anchors = [f'a wide brand banner strip in the palette carrying the line '
                                  f'"{line}" and the logo'], [line]
        elif key == "footer":
            tags = [str(t) for t in spec.get("footer_taglines") or []]
            need(tags, "footer_taglines")
            if tags:
                lines, anchors = ["footer line printed exactly: " + " | ".join(tags)], tags
        blocks.append({"key": key, "title": title, "required": required,
                       "present": bool(lines), "lines": lines, "anchors": anchors})
    if missing:
        raise BoardError("design board content missing (never invented): " + "; ".join(missing))
    return {"role": role, "spec": spec, "palette": palette, "fonts": fonts, "slots": slots,
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


def references(p: dict) -> list:
    refs = [p["logo"]] + [s["_path"] for s in p["slots"] if s["_path"]]
    return [str(r) for r in refs[:MAX_REFERENCES]]


def compose_prompt(p: dict, request: dict):
    """(prompt, sizes) for one board; sizes follow the executor's budget-band convention."""
    import stage_executor as se
    spec, role = p["spec"], p["role"]
    out = [f'DESIGN BOARD — one landscape ({BOARD_RATIO}) brand board sheet titled "'
           f'{spec["brand_name"]} — OFFICIAL VISUAL DIRECTION" for the client\'s '
           f'{ROLE_LABEL[role]}. It is the approval sheet shown before any wireframe: calm, '
           "editorial, generous spacing, every text string exactly as given below.",
           f"PAGE ROLE EMPHASIS — {ROLE_EMPHASIS[role]}."]
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
    refs = references(p)
    files = [x for x in p["slots"] if x["_path"]]
    planned = [x for x in p["slots"] if not x["_path"]] + files[MAX_REFERENCES - 1:]
    note = (f"REFERENCES — {len(refs)} attached: the client logo first, then the page's section "
            "images in slot order; use them exactly as given.")
    if planned:
        note += (" Slots with no attached file are drawn from their art direction and flagged in "
                 "the record: " + "; ".join(f'{x["slot_id"]} {x["art_direction"]}' for x in planned) + ".")
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


def foreign_hits(text: str, spec: dict) -> list:
    """Another client's brand text in `text`: the other clients' names (derived from the
    visual-standards manifest) and the example board's words. A name the run's own brand name
    contains is the client's own; a client named like the example may use its words."""
    import stage_executor as se
    own = norm(spec.get("brand_name"))
    terms = {norm(n) for n in se.cross_client_names()}
    if not any(t in own for t in EXAMPLE_TERMS):
        terms |= set(EXAMPLE_TERMS)
    body = norm(text)
    return sorted(t for t in terms if t and re.search(rf"\b{re.escape(t)}\b", body)
                  and not re.search(rf"\b{re.escape(t)}\b", own))


# ---------------------------------------------------------------- record

def write_record(run_dir: Path, p: dict, prompt: str, result: dict, revision: int):
    board = run_dir / BOARD_FILE
    iset = image_set(p["slots"])
    record = {
        "artifact": "design-board", "page_role": p["role"], "revision": revision,
        "brand": {"name": p["spec"]["brand_name"], "positioning_line": p["spec"]["positioning_line"],
                  "logo": {"file": str(p["logo"]), "sha256": sha256_file(p["logo"])}},
        "palette": p["palette"], "palette_sha256": canon_sha(p["palette"]),
        "palette_source": str(p["res"].source),
        "typography": {r: {"font": p["fonts"].get(r), **(p["spec"]["typography"].get(r) or {})}
                       for r, _ in TYPE_ROLES if (p["spec"]["typography"] or {}).get(r)},
        "image_set": iset,
        "reference_overflow": [s["slot_id"] for s in p["slots"] if s["_path"]][MAX_REFERENCES - 1:],
        "expected": p["expected"],
        "board": {"file": BOARD_FILE, "sha256": sha256_file(board), "ratio": BOARD_RATIO},
        "generation": {"provider": result.get("provider"), "mode": result.get("mode"),
                       "model": result.get("model"), "task_id": result.get("task_id"),
                       "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
                       "references": references(p), "generated_at": now_iso()},
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
    fails += readback_failures(rec)
    if require_approval:
        fails += approval_failures(rec)
    return fails


def image_set_failures(run_dir, rec, request_name) -> list:
    fails, recorded = [], (rec.get("image_set") or {}).get("slots") or []
    if (rec.get("image_set") or {}).get("sha256") != canon_sha(recorded):
        fails.append("design board: image set hash does not match the recorded slots")
    for s in recorded:
        if s.get("file"):
            fp = resolve_path(run_dir, s["file"])
            if fp is None or sha256_file(fp) != s.get("sha256"):
                fails.append(f"design board: image {s.get('slot_id')} changed or vanished since the board")
    try:
        request = read_json(run_dir / request_name)
    except BoardError:
        return fails  # no request on disk: the record is the authority
    now = {(str(sec.get("section_id")), str(sl.get("slot_id") or ""))
           for sec in request.get("sections") or [] for sl in sec.get("slots") or []}
    was = {(s.get("section_id"), s.get("slot_id")) for s in recorded}
    if now != was:
        fails.append("design board: the page's image slots changed since the board "
                     f"(added {sorted(now - was)}, removed {sorted(was - now)}); re-make and re-approve")
    return fails


def readback_failures(rec) -> list:
    rb = rec.get("readback")
    if not isinstance(rb, dict) or not str(rb.get("text") or "").strip() or not rb.get("native_resolution"):
        return ["design board: no native-resolution read-back recorded (design_board.py finalize)"]
    text, fails = norm(rb["text"]), []
    exp = rec.get("expected") or {}
    for block in exp.get("required_blocks") or []:
        anchors = (exp.get("anchors") or {}).get(block)
        if not anchors:
            fails.append(f"design board: required block {block!r} has no content recorded")
            continue
        absent = [a for a in anchors if norm(a) not in text]
        if absent:
            fails.append(f"design board: required block {block!r} is not legible on the board "
                         f"(read-back lacks {absent[:4]})")
    found = {h.upper() for h in HEX.findall(rb["text"])}
    want = set(exp.get("hexes") or [])
    if found - want:
        fails.append(f"design board: board prints colors outside the client palette: {sorted(found - want)}")
    if want - found:
        fails.append(f"design board: palette colors not printed on the board: {sorted(want - found)}")
    spec_like = {"brand_name": (rec.get("brand") or {}).get("name"),
                 "positioning_line": (rec.get("brand") or {}).get("positioning_line")}
    foreign = foreign_hits(rb["text"], spec_like)
    if foreign:
        fails.append("design board: board carries another client's brand text: " + ", ".join(foreign))
    return fails


def approval_failures(rec) -> list:
    ap = rec.get("approval")
    if not isinstance(ap, dict):
        return ["design board: no client approval recorded for this page's board "
                "(design_board.py approve); no wireframe or mockup stage may start"]
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
    rec = load_record(run_dir)
    rec["readback"] = {"native_resolution": True, "read_by": reader, "text": text,
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
            prompt, sizes = compose_prompt(plan(run_dir, request), request)
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
