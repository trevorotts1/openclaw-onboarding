#!/usr/bin/env python3
"""Hypersaturation: the page color system and the image color grade, as prompt blocks (Skill 71).

Owner order (Trevor Otts, 2026-10-19): "we use hyper saturation in our images - the blacks are
blacker, the reds are redder, the whites are whiter." GPT Image 2.5 through KIE rarely produces that
vibrancy on its own, so it is prompted, every time, built in, and always in the CLIENT's brand
colors. The rules and their evidence are references/hypersaturation-framework.md. This module is the
one place the wording lives:

  roles(palette, palette_roles=None)   hero / dark / light / accent from the client's resolved palette
  roles_for_run(run_dir)               the same, read from the run (scripts/brand_colors.py when present)
  page_block(roles, ground)            PAGE COLOR SYSTEM block for one section slice
  grade_block(roles)                   IMAGE COLOR GRADE block (Trevor's wording) for any image
  foreign_hexes(text, roles)           #hex colors in prose that are not the client's (callers refuse them)
  ground_for(index, section)           which of hero / dark / light this section sits on
  stage_blocks(stage, index, section, roles)   (page_block, grade_block) for a stage, or ("", "")

Nothing here names a hex. Every color is a slot filled from the client's palette; an example page's
red, green or tan can never reach a prompt. Pure standard library.

  python3 scripts/hypersaturation.py show --hero #HEX --dark #HEX --light #HEX [--accent #HEX]
      [--ground hero|dark|light]       print both blocks for a palette
"""
from __future__ import annotations

import argparse
import colorsys
import json
import re
import sys
from pathlib import Path

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
# Stages whose prompt makes the page itself (mockups) get both blocks; wireframes stay grayscale-plus-brand.
MOCKUP_STAGES = ("visual-mockup", "final-mockups")
# Ground order down the page: hero, light, dark, light, repeat. Neighbours always differ; across the two
# reference pages the grounds land at hero 20-23 %, dark 19-27 %, light 41-56 % of page height.
GROUND_CYCLE = ("hero", "light", "dark", "light")
GROUNDS = ("hero", "dark", "light")
MARKER_PAGE = "PAGE COLOR SYSTEM"
MARKER_GRADE = "IMAGE COLOR GRADE"


def _rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hsv(hex_color: str):
    r, g, b = (c / 255 for c in _rgb(hex_color))
    return colorsys.rgb_to_hsv(r, g, b)


def _luminance(hex_color: str) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _distance(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def color_name(hex_color: str) -> str:
    """A plain color word for the model ('deep blue'); the hex stays beside it."""
    h, s, v = _hsv(hex_color)
    if v < 0.18:
        return "near-black"
    deg = h * 360
    if s < 0.10:
        if v <= 0.9:
            return "grey"
        return "white" if s < 0.03 else "cream" if 30 <= deg <= 70 else "off-white"
    for limit, word in ((15, "red"), (40, "orange"), (65, "gold"), (95, "lime"), (165, "green"),
                        (195, "teal"), (255, "blue"), (290, "violet"), (335, "magenta"), (361, "red")):
        if deg < limit:
            base = word
            break
    weight = "deep " if v < 0.45 else "light " if (s < 0.35 and v > 0.85) else ""
    return weight + base


def _colors(palette: dict, palette_roles: dict | None):
    """Every distinct #RRGGBB the client's palette carries, hero candidates first."""
    values, seen = [], set()

    def add(v):
        if isinstance(v, str) and HEX.match(v) and v.upper() not in seen:
            seen.add(v.upper())
            values.append(v.upper())

    for source in (palette_roles or {}), (palette or {}):
        for v in source.values():
            for x in (v if isinstance(v, list) else [v]):
                add(x)
    return values


def roles(palette: dict, palette_roles: dict | None = None) -> dict:
    """hero (highest chroma), dark (darkest), light (lightest), accent (a distinct second chromatic
    color, else None). `palette_roles` is the primary / secondary / accent / background / text form
    scripts/brand_colors.py records; a plain palette dict works too. Raises ValueError when the
    palette has fewer than two usable colors: the page color system needs a hero and a neutral."""
    colors = _colors(palette, palette_roles)
    if len(colors) < 2:
        raise ValueError("the resolved palette has fewer than two #RRGGBB colors; "
                         "hypersaturation needs a hero color and a dark or light neutral")
    primary = (palette_roles or {}).get("primary")
    chroma = lambda c: _hsv(c)[1] * _hsv(c)[2]
    hero = primary.upper() if isinstance(primary, str) and HEX.match(primary) else max(colors, key=chroma)
    if chroma(hero) < 0.15:  # a neutral "primary": take the most chromatic color the palette has
        hero = max(colors, key=chroma)
    dark = min(colors, key=_luminance)
    light = max(colors, key=_luminance)
    accent = None
    pool = []
    if palette_roles:
        acc = palette_roles.get("accent")
        pool += [a for a in (acc if isinstance(acc, list) else [acc]) if isinstance(a, str)]
        pool.append(palette_roles.get("secondary"))
    pool += [c for c in colors]
    for c in pool:
        if not (isinstance(c, str) and HEX.match(c)):
            continue
        c = c.upper()
        if c in (hero, dark, light) or chroma(c) < 0.25:
            continue
        if _distance(c, hero) < 60:  # same family as the hero is not a second color
            continue
        accent = c
        break
    return {"hero": hero, "dark": dark, "light": light, "accent": accent, "palette": colors}


def roles_for_run(run_dir) -> dict | None:
    """The run's client roles, or None when no usable palette resolves (mockup and image stages then
    refuse). Uses scripts/brand_colors.py (the resolved-palette gate) when that module is present;
    otherwise stage_gate.brand_path_for_checked, with the file's brand_id tied to intake brand_owner."""
    run_dir = Path(run_dir)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import brand_colors  # SPF019: resolved client palette
    except ImportError:
        brand_colors = None
    if brand_colors is not None:
        res = brand_colors.resolve(run_dir)
        if not res.ok:
            return None
        palette, pr = res.palette, (res.brand or {}).get("palette_roles")
    else:
        # The stage gate's own lookup (private/brand.json, intake brand_file, skill default), so the
        # prompt and the gate never read different files; the file must belong to this run's client.
        import stage_gate
        try:
            owner = json.loads((run_dir / "intake.json").read_text(encoding="utf-8")).get("brand_owner")
            brand = json.loads(stage_gate.brand_path_for_checked(run_dir).read_text(encoding="utf-8"))
        except (OSError, ValueError, AttributeError):
            return None
        norm = lambda t: re.sub(r"[^a-z0-9]", "", str(t or "").lower())
        if not isinstance(brand, dict) or not isinstance(brand.get("palette"), dict):
            return None
        if not norm(owner) or norm(brand.get("brand_id")) != norm(owner):
            return None  # another client's palette is never used
        palette, pr = brand["palette"], brand.get("palette_roles")
    try:
        return roles(palette, pr if isinstance(pr, dict) else None)
    except ValueError:
        return None


ANY_HEX = re.compile(r"#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")


def foreign_hexes(text: str, r: dict) -> list:
    """Every #hex in `text` that is not one of the client's palette colors (sorted, upper case).
    Stage prose that names an old or example palette would fight the blocks above; callers refuse it."""
    allowed = {c.upper() for c in (r.get("palette") or [r["hero"], r["dark"], r["light"], r.get("accent")]) if c}
    found = {("#" + "".join(ch * 2 for ch in h[1:]) if len(h) == 4 else h).upper()
             for h in ANY_HEX.findall(text or "")}
    return sorted(found - allowed)


def ground_for(index: int, section: dict | None = None) -> str:
    """The ground a section sits on: the section's own `ground` when the plan pins one, else the
    rotation. Index is 1-based."""
    pinned = (section or {}).get("ground")
    if pinned in GROUNDS:
        return pinned
    return GROUND_CYCLE[(max(index, 1) - 1) % len(GROUND_CYCLE)]


def _label(hex_color: str) -> str:
    return f"{hex_color} ({color_name(hex_color)})"


def page_block(r: dict, ground: str) -> str:
    hero, dark, light, accent = r["hero"], r["dark"], r["light"], r.get("accent")
    ground_hex = r[ground]
    first = light if ground in ("dark", "hero") else dark
    second = dark if ground == "hero" else hero
    ink = max((dark, light), key=lambda c: _contrast(c, accent or hero))
    if accent:
        cta, cta_ink = accent, ink
        accent_rule = (f"the accent {_label(accent)} is small: the call-to-action fill, chips and badges, "
                       "and at most two small panels together under 7 percent of the page height; "
                       "it is never the hero color")
        colors = f"accent {_label(accent)}. "
    else:
        cta = dark if ground == "hero" else hero
        cta_ink = max((dark, light), key=lambda c: _contrast(c, cta))
        accent_rule = ("this palette has no second chromatic color, so do not invent one: the "
                       "call-to-action slab is the hero color on the dark and light grounds and the "
                       "dark color on the hero ground")
        colors = ""
    return (
        f"{MARKER_PAGE} - hypersaturated, the client's own colors only. Hero {_label(hero)} at full "
        f"saturation; dark {_label(dark)}; light {_label(light)}; {colors}"
        "This block wins over any other palette, grade or soft, warm, muted or ivory wording in this prompt. "
        f"THIS SLICE sits on the {ground.upper()} ground {ground_hex}; the sections above and below sit "
        "normally on different grounds. RULES: "
        "(1) the hero color owns the page: a flat full-bleed ground on roughly a quarter of the page, "
        "and also the second headline line, rules, bracket frames and the light inside photos. "
        "(2) Only three grounds, hero, dark and light, changing every section with hard butt joins: no "
        "pastel, blush, peach, cream-tint or grey grounds, no gradients between grounds, no haze. "
        f"(3) The light ground is exactly {light}, flat, clean and bright; the dark ground exactly {dark}, flat and deep; "
        "never a tinted, dimmed, yellowed or ivory-washed version of either. "
        f"(4) Headlines are heavy display type in two tones: first line {first}, second line or key word {second}. "
        "(5) A chapter or step change may take a full-width band of oversized repeated type in the hero color. "
        "(6) Photos are tight and backlit, graded to the hero color, bleeding to a page edge or filling "
        "their slot, with a hero-color device: an offset bracket or edge bar, a ring on a circle crop. "
        f"(7) The call-to-action is one solid slab {cta} with {cta_ink} text, the same design every time; "
        f"a seat or scarcity line under it is printed only when the verbatim copy carries one; {accent_rule}. "
        "(8) Every color is one of the colors named here or natural skin and photo content; never a "
        "color from any reference image.")


def grade_block(r: dict) -> str:
    hero, accent = r["hero"], r.get("accent")
    vivid = f"{_label(hero)} and {_label(accent)}" if accent else _label(hero)
    return (
        f"{MARKER_GRADE} - hyper-saturated cinematic color grade; deep true blacks, crushed shadows; vivid "
        f"fully saturated {vivid}; clean bright whites; high contrast, punchy midtones; strong directional "
        "key + rim light; luminous natural skin, true and rich, never tinted by the hero color. "
        "NEGATIVE - no muted, matte, faded, pastel, washed-out, flat or low-contrast grade, no grey haze, "
        "no warm ivory wash as the white.")


def stage_blocks(stage: str, index: int, section: dict | None, r: dict | None):
    """(page_block, grade_block) for one stage prompt; ("", "") when the stage is not a mockup stage
    or no client palette resolved."""
    if not r or stage not in MOCKUP_STAGES:
        return "", ""
    return page_block(r, ground_for(index, section)), grade_block(r)


def item_prompt(prompt: str, r: dict | None) -> str:
    """An image-slot prompt with the grade block prepended unless it already carries one."""
    if not r or MARKER_GRADE in prompt:
        return prompt
    return f"{grade_block(r)}\n\n{prompt}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--hero", required=True)
    s.add_argument("--dark", required=True)
    s.add_argument("--light", required=True)
    s.add_argument("--accent")
    s.add_argument("--ground", choices=GROUNDS, default="hero")
    a = p.parse_args(argv)
    for name in ("hero", "dark", "light", "accent"):
        v = getattr(a, name)
        if v and not HEX.match(v):
            print(f"FAIL: --{name} {v!r} is not #RRGGBB")
            return 2
    r = {"hero": a.hero.upper(), "dark": a.dark.upper(), "light": a.light.upper(),
         "accent": a.accent.upper() if a.accent else None}
    print(page_block(r, a.ground))
    print()
    print(grade_block(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
