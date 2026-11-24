#!/usr/bin/env python3
"""The run's closed font plan (font-action-plan/font-map.json) as printed type sizes (SWB-400 items 2 and 3).

The wireframe sheet prints a size beside every type element it draws. Until 1.3.54 nothing read the closed
font plan, so the sheet printed the house scale ("H2 48-64 px", "BODY 18-20 px") instead of the run's own sizes.
This module is the one reader of the font map's `typography` records:

  caption(font_map, element, stage)   "72 px desktop, 56 px tablet"  (the request's inline type spec)
  plan_specs(font_map, stage)         {h1, h2, body, cta}: family, size, line height per viewport
                                      (the section plan's `type_specs`, the W2 annotation record)

A wireframe element maps to one `typography` element of the font map: H1 hero_headline, H2 section_heading,
Body body, CTA cta_label. The desktop sheet states its desktop size and the tablet size; the mobile-tablet
sheet states the tablet size and the mobile size. An element the font map has no record for is never invented:
`caption` returns None and `plan_specs` refuses by name.

Never calls a provider and never reads a secret.
"""
from __future__ import annotations

import json
from pathlib import Path

FONT_MAP = Path("font-action-plan") / "font-map.json"
# wireframe element -> (font-map typography element, font-map role of the face)
ELEMENTS = {"H1": ("hero_headline", "display"), "H2": ("section_heading", "display"),
            "Body": ("body", "body"), "CTA": ("cta_label", "accent")}
VIEWPORTS = {"desktop-wireframe": ("desktop", "tablet"), "mobile-tablet": ("tablet", "mobile")}


class FontMapError(Exception):
    """A named refusal."""


def load(run_dir):
    """The run's font map, or None when the run has none. A file that cannot be read is a refusal."""
    path = Path(run_dir) / FONT_MAP
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FontMapError(f"{FONT_MAP} cannot be read: {exc}")
    if not isinstance(data, dict):
        raise FontMapError(f"{FONT_MAP} is not a JSON object")
    return data


def _record(font_map: dict, element: str):
    for entry in font_map.get("typography") or []:
        if isinstance(entry, dict) and entry.get("element") == element:
            return entry
    return None


def _size(record: dict, viewport: str):
    row = (record.get("sizes") or {}).get(viewport)
    px = row.get("px") if isinstance(row, dict) else None
    return (px, row.get("line_height")) if isinstance(px, (int, float)) and not isinstance(px, bool) and px > 0 else None


def caption(font_map: dict, element: str, stage: str):
    """'72 px desktop, 56 px tablet' for a wireframe element (H1, H2, Body, CTA), or None when the font map
    has no complete record for it at both of the stage's viewports."""
    if element not in ELEMENTS or stage not in VIEWPORTS:
        return None
    record = _record(font_map, ELEMENTS[element][0])
    if not record:
        return None
    parts = []
    for viewport in VIEWPORTS[stage]:
        size = _size(record, viewport)
        if size is None:
            return None
        parts.append(f"{size[0]:g} px {viewport}")
    return ", ".join(parts)


def _number(value) -> str:
    return f"{value:g}"


def plan_specs(font_map: dict, stage: str) -> dict:
    """The section plan's {h1, h2, body, cta} strings, e.g. 'Playfair Display 72px / 1.02 desktop, 56px / 1.05
    tablet'. Every element must have a complete record: the plan never states a size the font plan does not."""
    out = {}
    fonts = font_map.get("fonts") if isinstance(font_map.get("fonts"), dict) else {}
    for name, (element, role) in ELEMENTS.items():
        record = _record(font_map, element)
        if not record:
            raise FontMapError(f"{FONT_MAP} has no typography record for {element} ({name}); the section plan's "
                               "type specs come from it")
        family = fonts.get(record.get("role") or role) or fonts.get(role)
        if not family:
            raise FontMapError(f"{FONT_MAP} names no {record.get('role') or role} face for {element}")
        parts = []
        for viewport in VIEWPORTS[stage]:
            size = _size(record, viewport)
            if size is None:
                raise FontMapError(f"{FONT_MAP} typography {element} has no {viewport} size")
            line = f" / {_number(size[1])}" if size[1] else ""
            parts.append(f"{_number(size[0])}px{line} {viewport}")
        out[name.lower()] = f"{family} " + ", ".join(parts)
    return out


if __name__ == "__main__":
    raise SystemExit("font_sizes.py is a library; see scripts/write_section_plan.py")
