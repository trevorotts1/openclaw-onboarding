#!/usr/bin/env python3
"""Deterministically compose the Skill 71 overview boards.

Usage:
  python3 scripts/build_overview_board.py <run_dir> --stage STAGE
      [--device desktop|mobile|combined] [--request FILE] [--brand FILE]
      [--title TEXT] [--viewport-range TEXT] [--expect N] [--out-dir DIR]

Every image stage delivers views of the same sections: the long review PDF
(the whole page top to bottom) and the OVERVIEW BOARDS (all sections on one
big image). The contract is references/overview-board.md. Boards are written
to <run_dir>/review-pdfs/ next to the PDFs, each with a receipt (.json)
pinning the sha256 of every input:

  <stage>-desktop-overview.png   desktop board
  <stage>-mobile-overview.png    mobile board
  <name>-combined-overview.png   combined board: desktop and mobile together

  desktop   the full page as one tall column, top to bottom, beside a
            numbered SECTION GUIDE column (name, headline/body/CTA sizes,
            image ratio, thumbnail) aligned to each section.
  mobile    phone frames side by side, each with a "SECTIONS a-b" header
            and a caption under it naming what that part does, under a
            title band with the viewport-range note.
  combined  the desktop column and its guide, then the mobile page split
            into Part 1/3, 2/3, 3/3 columns (balanced, cut only between
            sections), all on one image. <name> is the stage id; the two
            wireframe stages share the name "wireframe" and the board is
            built once both have delivered (skipped until then).

The composer is pure code (Pillow): no generation, no network, no
randomness. It fails closed (exit 1, one FAIL line per fault, stale
boards removed) when a section image is missing, the numbering has a
gap, the image count differs from the run's section count (desktop and
mobile counts must match for the combined board), or the run carries no
section names. Section images are only ever scaled uniformly (one factor
for width and height); nothing is cropped or stretched.

Exit codes: 0 pass, 1 named failure, 2 usage / Pillow missing.
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_wireframe import hex_to_rgb, resolve_brand_path  # noqa: E402

DEFAULT_REQUEST = "production-request.json"
OUT_DIR = "review-pdfs"
VIEWPORT_RANGE = "320px \u2013 430px"  # SOP: check 320, 360, 390 and 430 CSS px

# stage -> [(device, section image template)]; the same file layout the
# stage executor writes (scripts/stage_executor.py LAYOUT).
STAGE_SETS = {
    "desktop-wireframe": [("desktop", "section-{n:02d}.png")],
    "mobile-tablet": [("mobile", "section-{n:02d}.png")],
    "visual-mockup": [("desktop", "desktop/part-{n:02d}.png"),
                      ("mobile", "mobile/part-{n:02d}.png")],
    "final-mockups": [("desktop", "desktop/part-{n:02d}.png"),
                      ("mobile", "mobile/part-{n:02d}.png")],
}
# stage -> (combined board name, desktop (stage, template), mobile (stage, template)).
# The two wireframe stages are two runs of one pair: the combined board is named
# for the pair and is built once both stages have delivered their images.
COMBINED_SETS = {
    "desktop-wireframe": ("wireframe", ("desktop-wireframe", "section-{n:02d}.png"), ("mobile-tablet", "section-{n:02d}.png")),
    "mobile-tablet": ("wireframe", ("desktop-wireframe", "section-{n:02d}.png"), ("mobile-tablet", "section-{n:02d}.png")),
    "visual-mockup": ("visual-mockup", ("visual-mockup", "desktop/part-{n:02d}.png"), ("visual-mockup", "mobile/part-{n:02d}.png")),
    "final-mockups": ("final-mockups", ("final-mockups", "desktop/part-{n:02d}.png"), ("final-mockups", "mobile/part-{n:02d}.png")),
}
STAGE_LABEL = {"desktop-wireframe": "WIREFRAME", "mobile-tablet": "WIREFRAME",
               "visual-mockup": "VISUAL MOCKUP", "final-mockups": "FINAL MOCKUP"}

# references/section-image-prompt.md "Type tokens": used, and starred on the
# board, only where the run recorded no per-section type spec.
SKILL_TYPE = {
    "desktop": {"headline": "H1 56\u201372px \u00b7 H2 48\u201364px", "body": "18\u201320px", "cta": "18\u201320px"},
    "mobile": {"headline": "34\u201348px", "body": "15\u201317px", "cta": "18\u201320px"},
}

# desktop layout (px)
D_MARGIN, D_PAGE_W, D_RAIL_W, D_GUIDE_W, D_BAND_H, D_HEAD_H = 40, 960, 72, 600, 150, 44
D_THUMB_W, D_THUMB_MAX_H, D_PAD, D_GAP = 168, 230, 18, 18
# mobile layout (px)
M_MARGIN, M_SCREEN_W, M_BEZEL, M_GAP, M_BAND_H, M_TAB_H = 36, 300, 11, 26, 160, 46
M_MAX_RATIO, M_MIN_RATIO = 2.8, 2.16  # frame content height / screen width: grouping limit, shortest phone
# combined board (desktop column + guide + mobile parts on one image)
C_PAGE_MIN, C_GUIDE_W, C_RAIL_W, C_COL_GAP = 560, 560, 56, 28
C_MOBILE_MIN, C_MOBILE_MAX, C_PARTS = 240, 520, 3

RATIOS = ["1:1", "5:4", "4:3", "3:2", "16:9", "2:1", "21:9", "3:1",
          "4:5", "3:4", "2:3", "9:16", "1:2", "9:21", "1:3"]

FONT_PATHS = {
    "serif": ["/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
              "C:/Windows/Fonts/georgiab.ttf"],
    "sans": ["/System/Library/Fonts/Supplemental/Arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "C:/Windows/Fonts/arial.ttf"],
    "bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "C:/Windows/Fonts/arialbd.ttf"],
}
_fonts, FONTS_USED = {}, set()


class BoardError(Exception):
    pass


# ---------------------------------------------------------------- data


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def discover(run_dir, stage, template, expect=None):
    """Ordered section image paths; BoardError on none, a gap, or a count mismatch."""
    stage_dir = run_dir / stage
    pattern = re.compile("^" + re.escape(template).replace(re.escape("{n:02d}"), r"(\d+)") + "$")
    folder = (stage_dir / template).parent
    found = {}
    for f in sorted(folder.glob("*.png")) if folder.is_dir() else []:
        m = pattern.match(str(f.relative_to(stage_dir)))
        if m:
            found[int(m.group(1))] = f
    if not found:
        raise BoardError(f"{stage}: no section images match {template.format(n=1)} in {stage_dir}")
    missing = [n for n in range(1, max(found) + 1) if n not in found]
    if missing:
        raise BoardError(f"{stage}: section image(s) {', '.join(f'{n:02d}' for n in missing)} missing "
                         f"(have {sorted(found)}); the board would drop a section")
    if expect is not None and len(found) != expect:
        raise BoardError(f"{stage}: {len(found)} section images for {expect} sections")
    return [found[n] for n in sorted(found)]


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _list(data):
    data = data.get("sections") if isinstance(data, dict) else data
    return [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []


def _cta(value):
    if isinstance(value, dict):
        value = value.get("label")
    return str(value or "").strip().rstrip(".")


def _slot_ratios(s):
    out = []
    labels = s.get("slot_labels")
    if isinstance(labels, dict):
        out += [(k, str(v.get("aspect_ratio"))) for k, v in labels.items()
                if isinstance(v, dict) and v.get("aspect_ratio")]
    for key in ("image_slots", "slots"):
        out += [(str(x.get("slot_id")), str(x.get("aspect_ratio"))) for x in (s.get(key) or [])
                if isinstance(x, dict) and x.get("aspect_ratio")]
    return out


def load_sections(run_dir, stage, request_name):
    """Per section: name, type_specs, declared slot ratios, cta.

    Priority per field: the stage's production-record.json, then its
    section-plan.json, then the run's production request. The request
    (the stage executor's own input) fixes the section order and count
    when present; otherwise the first source that has sections does.
    """
    stage_dir = run_dir / stage
    sources = [("production-record", stage_dir / "production-record.json"),
               ("section-plan", stage_dir / "section-plan.json"),
               ("production-request", run_dir / request_name)]
    loaded = [(label, _list(_read_json(p))) for label, p in sources if p.is_file()]
    loaded = [(label, secs) for label, secs in loaded if secs]
    if not loaded:
        raise BoardError(f"{stage}: no section names found (looked for {stage}/production-record.json, "
                         f"{stage}/section-plan.json, {request_name}); the board is named from the run")
    base = next((s for label, s in loaded if label == "production-request"), loaded[0][1])
    ids = [str(s.get("section_id") or f"S{i:02d}") for i, s in enumerate(base, start=1)]
    out = [{"id": sid} for sid in ids]
    by_id = {e["id"]: e for e in out}
    for label, secs in loaded:
        for s in secs:
            entry = by_id.get(str(s.get("section_id")))
            if entry is None:
                continue
            for key, value in (("name", str(s.get("section_name") or s.get("name") or "").strip()),
                               ("type_specs", s.get("type_specs") if isinstance(s.get("type_specs"), dict) else None),
                               ("slot_ratios", _slot_ratios(s)), ("cta", _cta(s.get("cta")))):
                if value and key not in entry:
                    entry[key] = value
                    entry.setdefault("sources", {})[key] = label
    for e in out:
        e.setdefault("name", e["id"])
    return out


def ratio_label(w, h):
    want = w / h
    best = min(RATIOS, key=lambda r: abs(int(r.split(":")[0]) / int(r.split(":")[1]) - want))
    got = int(best.split(":")[0]) / int(best.split(":")[1])
    err = abs(got - want) / want
    if err <= 0.01:
        return best
    return f"\u2248{best}" if err <= 0.04 else f"{want:.2f}:1"


def spec_lines(sec, device, size):
    """Guide lines for one section, plus True when a skill default was used."""
    ts, default, starred = sec.get("type_specs") or {}, SKILL_TYPE[device], False
    def pick(label, key, *keys):
        nonlocal starred
        value = next((str(ts[k]) for k in keys if ts.get(k)), None)
        if value is None and key == "headline" and (ts.get("h1") or ts.get("h2")):
            value = " \u00b7 ".join(f"{k.upper()} {ts[k]}" for k in ("h1", "h2") if ts.get(k))
        if value is None:
            value, starred = default[key], True
            return f"{label}: {value}*"
        return f"{label}: {value}"
    lines = [pick("Headline", "headline", "heading"), pick("Body", "body", "body"), pick("CTA", "cta", "cta")]
    slots = sec.get("slot_ratios") or []
    if slots:
        lines.append("Image: " + ", ".join(f"{r} ({sid})" for sid, r in slots))
    lines.append(f"Frame: {ratio_label(*size)} \u00b7 {size[0]}\u00d7{size[1]}px")
    return lines, starred


# -------------------------------------------------------------- chrome


def _lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def _contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _mix(a, b, t):
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _text_on(bg, light, dark):
    return light if _contrast(bg, light) >= _contrast(bg, dark) else dark


def chrome(run_dir, brand_arg):
    """Board chrome from the client's brand palette: lightest = ground, darkest
    = ink, most saturated of the rest = accent (the resolution order of
    validate_wireframe.resolve_brand_path)."""
    path = resolve_brand_path(run_dir, brand_arg)
    brand = _read_json(path)
    if not isinstance(brand, dict):
        raise BoardError(f"brand file {path} is missing or not a JSON object")
    palette = []
    for v in (brand.get("palette") or {}).values():
        rgb = hex_to_rgb(v)
        if rgb is not None and rgb not in palette:
            palette.append(rgb)
    if len(palette) < 2:
        raise BoardError(f"brand file {path} needs at least two palette hex colors for the board chrome")
    bg, ink = max(palette, key=_lum), min(palette, key=_lum)
    rest = [c for c in palette if c not in (bg, ink)]
    accent = max(rest, key=lambda c: colorsys.rgb_to_hsv(*[v / 255 for v in c])[1]) if rest else ink
    muted = _mix(bg, ink, 0.62)
    if _contrast(muted, bg) < 4.5:
        muted = ink
    return {"path": str(path), "brand_id": brand.get("brand_id"), "bg": bg, "ink": ink, "accent": accent,
            "tint": _mix(bg, accent, 0.12), "line": _mix(bg, ink, 0.25), "muted": muted,
            "on_ink": _text_on(ink, bg, (0, 0, 0)), "on_accent": _text_on(accent, bg, ink)}


# ------------------------------------------------------------- drawing


def font(kind, size):
    from PIL import ImageFont
    if (kind, size) not in _fonts:
        for p in FONT_PATHS[kind]:
            if os.path.isfile(p):
                _fonts[(kind, size)] = ImageFont.truetype(p, size)
                FONTS_USED.add(os.path.basename(p))
                break
        else:
            FONTS_USED.add("pillow-default")
            _fonts[(kind, size)] = ImageFont.load_default(size=size)
    return _fonts[(kind, size)]


def line_h(fnt):
    return int(getattr(fnt, "size", 11) * 1.32)


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for word in str(text).split():
        trial = f"{cur} {word}".strip()
        if cur and draw.textlength(trial, font=fnt) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur] if cur else lines or [""]


def text_block(draw, xy, lines, fnt, fill, center_w=None):
    x, y = xy
    for ln in lines:
        dx = (center_w - draw.textlength(ln, font=fnt)) / 2 if center_w else 0
        draw.text((x + dx, y), ln, font=fnt, fill=fill)
        y += line_h(fnt)
    return y


def scaled(im, width):
    """Uniform scale to `width` (one factor for both axes)."""
    from PIL import Image
    if im.width == width:
        return im
    return im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)


def fit_box(im, box_w, box_h):
    """Uniform scale so the image fits box_w x box_h; aspect preserved."""
    from PIL import Image
    s = min(box_w / im.width, box_h / im.height)
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)


def title_band(draw, W, H, c, title, subtitle, note=None):
    draw.rectangle([0, 0, W, H], fill=c["ink"])
    ft, fs = font("serif", 56), font("bold", 24)
    y = (H - 56 - 24 - 14) // 2
    draw.text((D_MARGIN, y), title.upper(), font=ft, fill=c["on_ink"])
    draw.text((D_MARGIN, y + 70), subtitle.upper(), font=fs, fill=_mix(c["ink"], c["on_ink"], 0.78))
    if note:
        fn = font("sans", 20)
        nw = int(max(draw.textlength(n, font=fn) for n in note)) + 48
        nh = line_h(fn) * len(note) + 36
        x0, y0 = W - D_MARGIN - nw, (H - nh) // 2
        draw.rounded_rectangle([x0, y0, x0 + nw, y0 + nh], 16, fill=c["tint"])
        text_block(draw, (x0 + 24, y0 + 18), note, fn, c["ink"])


# ------------------------------------------------------------- desktop


def split_parts(heights, k):
    """Consecutive split of section heights into at most k parts, cut only at
    section boundaries, minimizing the tallest part (ties: the earlier parts
    taller). Returns lists of 0-based section indexes."""
    from itertools import combinations
    n = len(heights)
    k = max(1, min(k, n))
    best = None
    for cuts in combinations(range(1, n), k - 1):
        edges = (0, *cuts, n)
        parts = [sum(heights[a:b]) for a, b in zip(edges, edges[1:])]
        key = (max(parts), [-h for h in parts])
        if best is None or key < best[0]:
            best = (key, edges)
    return [list(range(a, b)) for a, b in zip(best[1], best[1][1:])]


def build_desktop(imgs, secs, c, title, stage, mobile_imgs=None, viewport=None):
    """The desktop board; with mobile_imgs it is the COMBINED board: the same
    page column and section guide (narrower), then the mobile page split into
    Part 1/k .. k/k columns beside them."""
    from PIL import Image, ImageDraw
    combined = mobile_imgs is not None
    tmp = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    guide_w = C_GUIDE_W if combined else D_GUIDE_W
    f_name, f_spec, f_num = font("bold", 24), font("sans", 19), font("bold", 24)
    text_x = D_PAD + D_THUMB_W + D_PAD
    spec_w = guide_w - text_x - D_PAD
    cards, any_star = [], False
    for n, (sec, im) in enumerate(zip(secs, imgs), start=1):
        thumb = fit_box(im, D_THUMB_W, D_THUMB_MAX_H)
        lines, star = spec_lines(sec, "desktop", im.size)
        any_star |= star
        name_lines = wrap(tmp, sec["name"], f_name, guide_w - D_PAD * 2 - 52)
        spec_wrapped = [w for ln in lines for w in wrap(tmp, ln, f_spec, spec_w)]
        head_h = max(44, line_h(f_name) * len(name_lines))
        body_h = max(thumb.height, line_h(f_spec) * len(spec_wrapped))
        cards.append((thumb, name_lines, spec_wrapped, head_h, D_PAD + head_h + 12 + body_h + D_PAD))
    page_w, rail_w = D_PAGE_W, D_RAIL_W
    if combined:  # narrowest page column whose every section is tall enough for its guide card
        page_w, rail_w = C_PAGE_MIN, C_RAIL_W
        while page_w < D_PAGE_W and any(round(im.height * page_w / im.width) < cards[i][4] for i, im in enumerate(imgs)):
            page_w += 20
    pages = [scaled(im, page_w) for im in imgs]
    page_h = sum(p.height for p in pages)
    # mobile parts: consecutive, balanced, cut only between sections
    parts, m_w, m_pages = [], 0, []
    if combined:
        ratios = [im.height / im.width for im in mobile_imgs]
        parts = split_parts(ratios, C_PARTS)
        m_w = round(max(C_MOBILE_MIN, min(C_MOBILE_MAX, page_h / max(sum(ratios[i] for i in g) for g in parts))))
        m_pages = [scaled(im, m_w) for im in mobile_imgs]
    k = len(parts)
    # column headers (one wrapped line set; the tallest decides the bar height)
    f_head = font("bold", 22)
    kind = STAGE_LABEL[stage]
    heads = [(page_w, "FULL PAGE"), (guide_w, "SECTION GUIDE")]
    if combined:
        heads = [(page_w, f"DESKTOP {kind} ({len(imgs)} SECTIONS)"), (guide_w, "DESKTOP SECTION GUIDE")]
        heads += [(m_w, f"MOBILE {kind} (PART {i + 1}/{k})") for i in range(k)]
    head_lines = [wrap(tmp, t, f_head, w - 32) for w, t in heads]
    head_h = D_HEAD_H if not combined else max(len(hl) for hl in head_lines) * line_h(f_head) + 24
    top = D_BAND_H + head_h + 24
    y, ys, tops = top, [], []
    for p in pages:  # section tops on the page column
        tops.append(y)
        y += p.height
    page_bottom = y
    cy = top
    for (_t, _n, _s, _h, h), t in zip(cards, tops):  # guide cards, never overlapping
        cy = max(t, cy)
        ys.append(cy)
        cy += h + D_GAP
    guide_bottom = cy - D_GAP
    m_tops = []  # per part: y of each of its sections
    m_bottom = 0
    for g in parts:
        yy, col = top, []
        for i in g:
            col.append(yy)
            yy += m_pages[i].height
        m_tops.append(col)
        m_bottom = max(m_bottom, yy)
    bottom = max(page_bottom, guide_bottom, m_bottom)
    foot = [("* Type sizes marked with an asterisk are the skill standard "
             "(references/section-image-prompt.md); this run recorded no per-section value.")] if any_star else []
    foot.append("Section images are scaled uniformly; nothing is cropped or stretched.")
    f_foot = font("sans", 17)
    px = D_MARGIN
    gx = px + page_w + rail_w
    mxs = []
    mx = gx + guide_w + C_COL_GAP
    for _g in parts:
        mxs.append(mx)
        mx += m_w + C_RAIL_W + C_COL_GAP
    W = D_MARGIN * 2 + page_w + rail_w + guide_w
    if combined:
        W = mx - C_COL_GAP + D_MARGIN
        subtitle = f"Desktop + Mobile {kind} \u00b7 {len(imgs)} sections \u00b7 desktop page, guide and mobile page"
        note = [f"Optimized for mobile ({viewport or VIEWPORT_RANGE})", "Desktop page left, mobile page in parts right"]
        left_w = max(tmp.textlength(title.upper(), font=font("serif", 56)), tmp.textlength(subtitle.upper(), font=font("bold", 24)))
        W = int(max(W, left_w + 48 + 40 + max(tmp.textlength(n, font=font("sans", 20)) for n in note) + 48 + D_MARGIN * 2))
    else:
        subtitle, note = f"Desktop {kind} \u00b7 {len(imgs)} sections \u00b7 full page, top to bottom", None
    H = bottom + 28 + line_h(f_foot) * len(foot) + D_MARGIN
    board = Image.new("RGB", (W, H), c["bg"])
    d = ImageDraw.Draw(board)
    title_band(d, W, D_BAND_H, c, title, subtitle, note)
    for x, (w, _t), hl in zip([px, gx] + mxs, heads, head_lines):
        d.rectangle([x, D_BAND_H + 12, x + w, D_BAND_H + 12 + head_h - 8], fill=c["accent"])
        text_block(d, (x + 16, D_BAND_H + 22 if not combined else D_BAND_H + 12 + 8), hl, f_head, c["on_accent"])

    def rail(x, w, rw, column, numbers, col_tops):
        for n, p, t in zip(numbers, column, col_tops):
            board.paste(p, (x, t))
            rx = x + w + rw // 2
            d.line([rx, t + 40, rx, t + p.height - 6], fill=c["line"], width=3)
            d.ellipse([rx - 22, t + 4, rx + 22, t + 48], fill=c["accent"])
            d.text((rx - d.textlength(str(n), font=f_num) / 2, t + 12), str(n), font=f_num, fill=c["on_accent"])

    rail(px, page_w, rail_w, pages, range(1, len(pages) + 1), tops)
    for n, ((thumb, name_lines, spec_wrapped, hh, ch), cy) in enumerate(zip(cards, ys), start=1):
        d.rounded_rectangle([gx, cy, gx + guide_w, cy + ch], 14, fill=c["tint"], outline=c["line"], width=2)
        d.ellipse([gx + D_PAD, cy + D_PAD, gx + D_PAD + 40, cy + D_PAD + 40], fill=c["accent"])
        d.text((gx + D_PAD + 20 - d.textlength(str(n), font=f_num) / 2, cy + D_PAD + 6), str(n), font=f_num, fill=c["on_accent"])
        text_block(d, (gx + D_PAD + 54, cy + D_PAD + 6), name_lines, f_name, c["ink"])
        by = cy + D_PAD + hh + 12
        board.paste(thumb, (gx + D_PAD, by))
        d.rectangle([gx + D_PAD - 1, by - 1, gx + D_PAD + thumb.width, by + thumb.height], outline=c["line"])
        text_block(d, (gx + text_x, by), spec_wrapped, f_spec, c["ink"])
    for x, g, col in zip(mxs, parts, m_tops):
        rail(x, m_w, C_RAIL_W, [m_pages[i] for i in g], [i + 1 for i in g], col)
    fy = bottom + 28
    for ln in foot:
        d.text((D_MARGIN, fy), ln, font=f_foot, fill=c["muted"])
        fy += line_h(f_foot)
    geometry = {"layout": "combined" if combined else "desktop", "page_x": px, "page_column_width": page_w,
                "sections": [{"number": n, "id": s["id"], "page_y": t, "guide_y": g}
                             for n, (s, t, g) in enumerate(zip(secs, tops, ys), start=1)]}
    if combined:
        geometry["mobile_column_width"] = m_w
        geometry["mobile_parts"] = [{"label": f"PART {i + 1}/{k}", "x": x, "sections": [secs[j]["id"] for j in g],
                                     "section_y": col}
                                    for i, (g, col, x) in enumerate(zip(parts, m_tops, mxs))]
    return board, geometry


# -------------------------------------------------------------- mobile


def group_sections(heights, max_h):
    """Greedy, in section order: a section joins the current frame while the
    frame's content stays within max_h; a section taller than max_h gets a
    frame to itself. Returns lists of 0-based section indexes."""
    groups, cur, used = [], [], 0
    for i, h in enumerate(heights):
        if cur and used + h > max_h:
            groups.append(cur)
            cur, used = [], 0
        cur.append(i)
        used += h
    return groups + [cur] if cur else groups


def build_mobile(imgs, secs, c, title, stage, viewport):
    from PIL import Image, ImageDraw
    tmp = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    pages = [scaled(im, M_SCREEN_W) for im in imgs]
    groups = group_sections([p.height for p in pages], round(M_MAX_RATIO * M_SCREEN_W))
    screen_h = max(round(M_MIN_RATIO * M_SCREEN_W), max(sum(pages[i].height for i in g) for g in groups))
    fw, fh = M_SCREEN_W + 2 * M_BEZEL, screen_h + 2 * M_BEZEL
    f_tab, f_cap, f_sub = font("bold", 22), font("bold", 20), font("sans", 17)
    caps = []
    for g in groups:
        names = wrap(tmp, " & ".join(secs[i]["name"] for i in g), f_cap, fw - 28)
        ctas = list(dict.fromkeys(secs[i]["cta"] for i in g if secs[i].get("cta")))
        sub = wrap(tmp, "CTA: " + " / ".join(ctas), f_sub, fw - 28) if ctas else []
        caps.append((names, sub))
    cap_h = max(line_h(f_cap) * len(n) + line_h(f_sub) * len(s) for n, s in caps) + 28
    n_f = len(groups)
    note = [f"Optimized for mobile ({viewport})", "Same content and flow as desktop \u00b7 No section labels on the page"]
    subtitle = f"Mobile {STAGE_LABEL[stage]} (complete scroll)"
    # the left block is as wide as the longer of title and subtitle; the note box sits right of it
    left_w = max(tmp.textlength(title.upper(), font=font("serif", 56)),
                 tmp.textlength(subtitle.upper(), font=font("bold", 24)))
    head_w = (left_w + 48 + 40 +
              max(tmp.textlength(n, font=font("sans", 20)) for n in note) + 48 + D_MARGIN * 2)
    W = int(max(head_w, M_MARGIN * 2 + n_f * fw + (n_f - 1) * M_GAP))
    top = M_BAND_H + 32
    H = top + M_TAB_H + fh + 12 + cap_h + M_MARGIN
    board = Image.new("RGB", (W, H), c["bg"])
    d = ImageDraw.Draw(board)
    title_band(d, W, M_BAND_H, c, title, subtitle, note)
    x0 = (W - (n_f * fw + (n_f - 1) * M_GAP)) // 2
    meta = []
    for k, (g, (names, sub)) in enumerate(zip(groups, caps)):
        x = x0 + k * (fw + M_GAP)
        label = f"SECTION {g[0] + 1}" if len(g) == 1 else f"SECTIONS {g[0] + 1}-{g[-1] + 1}"
        d.rounded_rectangle([x, top, x + fw, top + M_TAB_H + 20], 14, fill=c["accent"])
        d.text((x + (fw - d.textlength(label, font=f_tab)) / 2, top + 11), label, font=f_tab, fill=c["on_accent"])
        fy = top + M_TAB_H
        d.rounded_rectangle([x, fy, x + fw, fy + fh], 40, fill=c["ink"])
        d.rounded_rectangle([x + fw // 2 - 36, fy + 3, x + fw // 2 + 36, fy + 9], 3, fill=_mix(c["ink"], c["bg"], 0.35))
        screen = Image.new("RGB", (M_SCREEN_W, screen_h), c["bg"])
        yy = 0
        for i in g:
            screen.paste(pages[i], (0, yy))
            yy += pages[i].height
        mask = Image.new("L", screen.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, screen.width - 1, screen.height - 1], 30, fill=255)
        board.paste(screen, (x + M_BEZEL, fy + M_BEZEL), mask)
        cy = fy + fh + 12
        d.rounded_rectangle([x, cy, x + fw, cy + cap_h], 18, fill=c["tint"])
        ty = text_block(d, (x + 14, cy + 14), names, f_cap, c["ink"], center_w=fw - 28)
        text_block(d, (x + 14, ty), sub, f_sub, c["muted"], center_w=fw - 28)
        meta.append({"label": label, "sections": [secs[i]["id"] for i in g]})
    return board, {"layout": "mobile", "screen_width": M_SCREEN_W, "frames": meta}


# ---------------------------------------------------------------- main


def load_images(run_dir, stage, template, expect):
    """(paths, RGB images) for one device's section images; BoardError on any fault."""
    from PIL import Image
    paths = discover(run_dir, stage, template, expect)
    imgs = []
    for p in paths:
        try:
            with Image.open(p) as im:
                imgs.append(im.convert("RGB"))
        except Exception as exc:
            raise BoardError(f"{stage}: section image {p.name} is not a readable image ({exc})")
    return paths, imgs


def write_board(board, name, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".png", dir=out_dir)
    os.close(fd)
    board.save(tmp, "PNG")  # no metadata, no timestamps: identical inputs give identical bytes
    os.chmod(tmp, 0o644)
    os.replace(tmp, out_dir / f"{name}.png")


def write_receipt(out_dir, name, board, stage, device, secs, inputs, c, geometry, run_dir):
    """inputs: [(device, paths, imgs)] in the order the receipt lists them."""
    def one(inp, n):  # a single device keeps the flat per-section keys of the first contract
        _dv, paths, imgs = inp
        return {"image": os.path.relpath(paths[n - 1], run_dir), "native_size": list(imgs[n - 1].size),
                "sha256": sha256(paths[n - 1])}

    receipt = {
        "board": f"{name}.png", "stage": stage, "device": device,
        "size": {"width": board.width, "height": board.height},
        "output_sha256": sha256(out_dir / f"{name}.png"),
        "sections": [dict({"number": n, "id": s["id"], "name": s["name"]},
                          **(one(inputs[0], n) if len(inputs) == 1 else
                             {"images": [dict(device=dv, **one((dv, paths, imgs), n)) for dv, paths, imgs in inputs]}),
                          field_sources=s.get("sources", {}))
                     for n, s in enumerate(secs, start=1)],
        "chrome": {k: (list(v) if isinstance(v, tuple) else v) for k, v in c.items()},
        "fonts": sorted(FONTS_USED), "geometry": geometry,
    }
    (out_dir / f"{name}.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def build_device(run_dir, stage, device, template, secs, c, title, viewport, out_dir, expect):
    paths, imgs = load_images(run_dir, stage, template, expect if expect is not None else len(secs))
    if device == "desktop":
        board, geometry = build_desktop(imgs, secs, c, title, stage)
    else:
        board, geometry = build_mobile(imgs, secs, c, title, stage, viewport)
    name = f"{stage}-{device}-overview"
    write_board(board, name, out_dir)
    write_receipt(out_dir, name, board, stage, device, secs, [(device, paths, imgs)], c, geometry, run_dir)
    return out_dir / f"{name}.png", board.size


def build_combined(run_dir, stage, secs, c, title, viewport, out_dir, expect, required):
    """The all-in-one board: desktop and mobile of the same sections on one image.

    Returns None (skipped) when the other wireframe stage's set is not complete
    yet (nothing, a gap, or fewer images than sections) and `required` is False:
    its own run builds the board. Raises BoardError for any fault in this stage's
    own images, with `required`, or when the sibling holds more images than
    sections (a real count mismatch)."""
    name, (d_stage, d_tpl), (m_stage, m_tpl) = COMBINED_SETS[stage]
    want = expect if expect is not None else len(secs)
    loaded = {}
    for dv, st, tpl in (("desktop", d_stage, d_tpl), ("mobile", m_stage, m_tpl)):
        try:
            loaded[dv] = load_images(run_dir, st, tpl, want)
        except BoardError:
            if st == stage or required:
                raise
            try:
                surplus = len(discover(run_dir, st, tpl)) > want
            except BoardError:
                surplus = False  # none or a gap: not delivered yet
            if surplus:
                raise
            return None  # sibling set incomplete; the stage that finishes it builds the board
    board, geometry = build_desktop(loaded["desktop"][1], secs, c, title, d_stage, loaded["mobile"][1], viewport)
    write_board(board, f"{name}-combined-overview", out_dir)
    write_receipt(out_dir, f"{name}-combined-overview", board, name, "combined", secs,
                  [("desktop", *loaded["desktop"]), ("mobile", *loaded["mobile"])], c, geometry, run_dir)
    return out_dir / f"{name}-combined-overview.png", board.size


def build_stage(run_dir, stage, device=None, request=DEFAULT_REQUEST, brand=None, title=None,
                viewport=None, expect=None, out_dir=None):
    """Build every board the stage owes. Returns [(path, (w, h))]; raises BoardError.

    The separate desktop and mobile boards come first, then the combined
    all-in-one board. A failure removes the stage's existing boards so a stale
    board never ships.
    """
    run_dir = Path(run_dir).resolve()
    out = Path(out_dir) if out_dir else run_dir / OUT_DIR
    sets = [(d, t) for d, t in STAGE_SETS[stage] if device in (None, "combined", d)]
    if device == "combined":
        sets = []
    elif not sets:
        raise BoardError(f"{stage} has no {device} images")
    cname = COMBINED_SETS[stage][0]
    try:
        c = chrome(run_dir, brand)
        secs = load_sections(run_dir, stage, request)
        title = title or (c.get("brand_id") or "Signature page")
        built = [build_device(run_dir, stage, d, t, secs, c, title, viewport or VIEWPORT_RANGE, out, expect)
                 for d, t in sets]
        if device in (None, "combined"):
            d_stage = COMBINED_SETS[stage][1][0]  # the guide is the desktop guide: desktop-stage records first
            try:
                csecs = secs if d_stage == stage else load_sections(run_dir, d_stage, request)
            except BoardError:
                csecs = secs
            combined = build_combined(run_dir, stage, csecs, c, title, viewport or VIEWPORT_RANGE, out, expect,
                                      required=device == "combined")
            if combined:
                built.append(combined)
            else:  # skipped: an older combined board no longer matches this stage's images
                for ext in ("png", "json"):
                    (out / f"{cname}-combined-overview.{ext}").unlink(missing_ok=True)
        return built
    except BoardError:
        for n in [f"{stage}-{d}-overview" for d, _t in sets] + [f"{cname}-combined-overview"]:
            for ext in ("png", "json"):
                (out / f"{n}.{ext}").unlink(missing_ok=True)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description="Compose a stage's combined overview boards (desktop and mobile).")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--stage", required=True, choices=sorted(STAGE_SETS))
    p.add_argument("--device", choices=["desktop", "mobile", "combined"])
    p.add_argument("--request", default=DEFAULT_REQUEST,
                   help="production request inside the run dir (section names, copy, CTA)")
    p.add_argument("--brand", default=None, help="brand JSON for the chrome colors (default: the run's pinned brand)")
    p.add_argument("--title", default=None, help="title band text (default: the brand id)")
    p.add_argument("--viewport-range", default=None, help=f"mobile note (default {VIEWPORT_RANGE})")
    p.add_argument("--expect", type=int, default=None, help="expected section count")
    p.add_argument("--out-dir", type=Path, default=None, help=f"default <run_dir>/{OUT_DIR}")
    a = p.parse_args(argv)
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("FAIL: Pillow is required. Install the Python package 'Pillow' in this runtime.")
        return 2
    try:
        built = build_stage(a.run_dir, a.stage, a.device, a.request, a.brand, a.title,
                            a.viewport_range, a.expect, a.out_dir)
    except BoardError as exc:
        print(f"FAIL: {exc}")
        return 1
    for path, (w, h) in built:
        print(f"PASS: overview board {path} ({w}x{h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
