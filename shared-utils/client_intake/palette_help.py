#!/usr/bin/env python3
"""Colour help for a client who does not know their brand colours.

Three ways to help, none needs a browser, a paid call or a model:
  extract_from_logo(path)      read the main colours of a logo file (Pillow)
  extract_from_website(url)    read colours from the page HTML and CSS (plain HTTP fetch)
  suggest_palettes(seed, mood) three palettes with roles, a plain-English reason and an example
plus safe_default(), the neutral palette that belongs to no client.

Every function returns plain dicts. Hex values are always upper-case #RRGGBB.
CLI:  palette_help.py logo FILE | site URL | suggest [--seed HEX] [--mood "warm friendly"] | default
"""
from __future__ import annotations

import colorsys
import ipaddress
import json
import re
import socket
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

DEFAULTS = json.loads((Path(__file__).with_name("palette-defaults.json")).read_text(encoding="utf-8"))
HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
# ponytail: 24 everyday names; anything else is asked back as a color code, upgrade by extending this table.
NAMES = {
    "black": "#000000", "white": "#FFFFFF", "red": "#D62828", "orange": "#F77F00", "yellow": "#FCBF49",
    "green": "#2E8B57", "teal": "#0A7E8C", "blue": "#1D4ED8", "navy": "#1B2A4A", "navy blue": "#1B2A4A",
    "purple": "#6B3FA0", "violet": "#6B3FA0", "pink": "#E5568C", "brown": "#7B4B2A", "gray": "#808080",
    "grey": "#808080", "gold": "#C9A227", "silver": "#C0C0C0", "cream": "#F5F0E8", "beige": "#E8DCC8",
    "burgundy": "#7A1F3D", "coral": "#E76F51", "turquoise": "#2EC4B6", "maroon": "#800000",
}
ROLE_WORDS = {"primary": "primary", "main": "primary", "secondary": "secondary", "second": "secondary",
              "accent": "accent", "highlight": "accent", "background": "background", "bg": "background", "text": "text"}
_ROLE_RE = re.compile(r"\b(primary|main|secondary|second|accent|highlight|background|bg|text)\b(?:\s*colou?r)?\s*[:=\-]?\s*"
                      r"(#[0-9a-fA-F]{3,6}\b|[a-z]+(?: blue)?)", re.I)


def normalize_hex(text):
    """'#abc', 'ABC123' -> '#AABBCC' / '#ABC123'; None when it is not a color code."""
    t = str(text).strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{3}", t):
        t = "".join(c * 2 for c in t)
    return "#" + t.upper() if re.fullmatch(r"[0-9a-fA-F]{6}", t) else None


def to_hex(token):
    """A color code or a known color name -> hex, else None."""
    return normalize_hex(token) or NAMES.get(re.sub(r"\s+", " ", str(token).strip().lower()))


def parse_colors(text):
    """Read what a client typed. Returns {"colors": [hex..], "roles": {role: hex}, "unknown": [words]}.
    'primary #123456, background white' fills roles; plain lists fill colors only."""
    text = str(text or "")
    roles, colors, unknown = {}, [], []
    for role_word, token in _ROLE_RE.findall(text):
        h = to_hex(token)
        if h:
            role = ROLE_WORDS[role_word.lower()]
            if role == "accent":
                roles.setdefault("accent", []).append(h)
            elif role == "background":
                roles.setdefault("background", []).append(h)
            else:
                roles.setdefault(role, h)
    found = [(m.start(), normalize_hex(m.group(0))) for m in HEX_RE.finditer(text)]
    low = text.lower()
    for name in sorted(NAMES, key=len, reverse=True):  # 'navy blue' before 'navy'
        for m in re.finditer(rf"\b{re.escape(name)}\b", low):
            found.append((m.start(), NAMES[name]))
            low = low[:m.start()] + " " * len(name) + low[m.end():]
    for _, h in sorted(found):
        if h not in colors:
            colors.append(h)
    stop = {"and", "or", "with", "my", "is", "are", "the", "a", "color", "colors", "colour", "colours", "i", "it", "of", "then", "plus"}
    for w in re.findall(r"[a-zA-Z]+", re.sub(HEX_RE, " ", low)):
        if w not in stop and w not in ROLE_WORDS and not any(w in n.split() for n in NAMES):
            unknown.append(w)
    return {"colors": colors, "roles": roles, "unknown": unknown}


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def luminance(h):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def check_palette(roles):
    """Plain-English warnings; an empty list means readable. Never blocks."""
    out, bg = [], (roles.get("background") or ["#FFFFFF"])[0]
    if roles.get("text") and contrast_ratio(roles["text"], bg) < 4.5:
        out.append(f"Text {roles['text']} on background {bg} is hard to read (contrast {contrast_ratio(roles['text'], bg)}, want 4.5 or more).")
    if roles.get("primary") and contrast_ratio(roles["primary"], bg) < 3:
        out.append(f"Main color {roles['primary']} on background {bg} is faint for buttons (contrast {contrast_ratio(roles['primary'], bg)}, want 3 or more).")
    return out


def readable_text_for(background):
    return "#1A1A1A" if luminance(background) > 0.4 else "#FFFFFF"


def _swatches(hexes):
    return [h for h in hexes if h]


def _saturated(h):
    r, g, b = (v / 255 for v in _rgb(h))
    _, s, v = colorsys.rgb_to_hsv(r, g, b)
    return s > 0.2 and 0.12 < v < 0.97


def _rank(counter, n):
    """Most common first; near-white and grey only fill leftover slots."""
    items = counter.most_common()
    keep = [h for h, _ in items if _saturated(h)]
    keep += [h for h, _ in items if h not in keep]
    return keep[:n]


def extract_from_logo(path, n=4):
    """Main colours of a logo image, most used first. Needs Pillow (already required by Skill 71)."""
    from PIL import Image  # imported here so the rest of the module works without Pillow

    im = Image.open(path).convert("RGBA")
    im.thumbnail((120, 120))
    flat = Image.new("RGB", im.size, (255, 255, 255))
    solid = Image.new("L", im.size, 0)
    solid.putdata([255 if p[3] > 200 else 0 for p in im.getdata()])
    flat.paste(im.convert("RGB"), mask=solid)
    q = flat.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counter = Counter()
    for count, idx in q.getcolors():
        counter["#%02X%02X%02X" % tuple(pal[idx * 3:idx * 3 + 3])] += count
    # drop the white we pasted behind a transparent logo
    counter.pop("#FFFFFF", None) if any(p[3] < 200 for p in im.getdata()) else None
    colors = _rank(counter, n)
    return {"source": "logo", "colors": colors, "suggested_primary": colors[0] if colors else None}


_PRIVATE_NOTE = "That address points to a private or local network, so I cannot read it. Please send the colors or a logo file instead."


def _public_host_ok(url):
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except OSError:
        return False
    return all(not (ipaddress.ip_address(i[4][0]).is_private or ipaddress.ip_address(i[4][0]).is_loopback
                    or ipaddress.ip_address(i[4][0]).is_link_local or ipaddress.ip_address(i[4][0]).is_reserved) for i in infos)


def http_fetch(url, limit=1_000_000, timeout=10):
    """Plain HTTP GET of text (HTML or CSS). No browser, no scripts run."""
    if not _public_host_ok(url):
        raise ValueError(_PRIVATE_NOTE)
    req = urllib.request.Request(url, headers={"User-Agent": "client-intake-palette-help/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (scheme checked above)
        return r.read(limit).decode("utf-8", "replace")


def extract_from_website(url, n=4, fetch=None):
    """Colours used by a website: theme-color, CSS custom properties, then the most frequent hex codes.
    `fetch(url) -> text` is injectable so tests and offline runs never touch the network."""
    fetch = fetch or http_fetch
    html = fetch(url)
    texts = [html]
    for href in re.findall(r"<link[^>]+rel=[\"']stylesheet[\"'][^>]*href=[\"']([^\"']+)", html, re.I)[:3]:
        try:
            texts.append(fetch(urllib.parse.urljoin(url, href)))
        except (OSError, ValueError):
            continue
    blob = "\n".join(texts)
    counter = Counter()
    theme = re.search(r"<meta[^>]+name=[\"']theme-color[\"'][^>]*content=[\"'](#[0-9a-fA-F]{3,6})", html, re.I)
    first = [normalize_hex(theme.group(1))] if theme else []
    for var in re.findall(r"--(?:primary|brand|main|accent)[\w-]*\s*:\s*(#[0-9a-fA-F]{3,6})", blob, re.I):
        first.append(normalize_hex(var))
    for m in HEX_RE.finditer(blob):
        counter[normalize_hex(m.group(0))] += 1
    ranked = _rank(counter, n * 2)
    colors = []
    for h in [h for h in first if h] + ranked:
        if h and h not in colors:
            colors.append(h)
    colors = colors[:n]
    return {"source": "website", "url": url, "colors": colors, "suggested_primary": colors[0] if colors else None}


def _shift(h, dh=0.0, ds=1.0, dv=1.0):
    r, g, b = (v / 255 for v in _rgb(h))
    hh, s, v = colorsys.rgb_to_hsv(r, g, b)
    r, g, b = colorsys.hsv_to_rgb((hh + dh) % 1.0, min(1, s * ds), min(1, v * dv))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _make(name, roles, reason, example):
    roles = dict(roles)
    roles["text"] = roles.get("text") or readable_text_for(roles["background"][0])
    return {"name": name, "roles": roles, "reason": reason, "example": example, "warnings": check_palette(roles)}


def suggest_palettes(seed=None, mood=""):
    """Always three palettes. With a seed color they are built around it (matching, contrasting, calm);
    without one they are the curated set, the one that fits `mood` words listed first."""
    if seed and normalize_hex(seed):
        s = normalize_hex(seed)
        dark = readable_text_for("#FFFFFF")
        return [
            _make("Matching shades", {"primary": s, "secondary": _shift(s, 0, 0.25, 1.15), "accent": [_shift(s, 0.04, 0.9, 1.0)], "background": ["#FFFFFF"], "text": dark},
                  "Different shades of your own color. Everything looks like one family.", "Like a brand that stays calm and consistent."),
            _make("Pop of contrast", {"primary": s, "secondary": _shift(s, 0, 0.2, 1.2), "accent": [_shift(s, 0.5, 0.85, 0.95)], "background": ["#FFFFFF"], "text": dark},
                  "A highlight from the opposite side of the color wheel makes buttons stand out.", "Like a brand that wants to be noticed."),
            _make("Soft and warm", {"primary": s, "secondary": "#F3EDE4", "accent": [_shift(s, -0.08, 0.7, 1.0)], "background": ["#FFFAF4"], "text": "#2B2622"},
                  "Your color on a warm off-white. Friendly and easy on the eyes.", "Like a boutique or a coach people already trust."),
        ]
    words = set(re.findall(r"[a-z]+", str(mood).lower()))
    ranked = sorted(DEFAULTS["suggested"], key=lambda p: -len(words & set(p["mood"])))
    return [_make(p["name"], p["roles"], p["reason"], p["example"]) for p in ranked[:3]]


def safe_default():
    d = DEFAULTS["safe_default"]
    return {"name": d["name"], "roles": json.loads(json.dumps(d["roles"])), "reason": d["reason"], "warnings": check_palette(d["roles"])}


def fonts_suggestions():
    return [dict(p) for p in DEFAULTS["font_pairs"]]


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) >= 2 and a[0] == "logo":
        out = extract_from_logo(a[1])
    elif len(a) >= 2 and a[0] == "site":
        out = extract_from_website(a[1])
    elif a[:1] == ["suggest"]:
        seed = a[a.index("--seed") + 1] if "--seed" in a else None
        mood = a[a.index("--mood") + 1] if "--mood" in a else ""
        out = suggest_palettes(seed, mood)
    elif a[:1] == ["default"]:
        out = safe_default()
    else:
        print(__doc__)
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
