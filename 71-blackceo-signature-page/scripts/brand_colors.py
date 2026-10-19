#!/usr/bin/env python3
"""Brand-color resolution: the gate every wireframe, mockup and image stage passes first.

Trevor's rule: every wireframe and mockup is in the CLIENT's own brand colors. The skill
first looks for colors it already knows, and only when none are known does it ask the
client. It never guesses, and never falls back to a default or another client's palette.

Ordered resolution (first source that yields a usable, owned palette wins):
  1. <run_dir>/private/brand.json      the run's pinned brand file
  2. intake.json -> brand_file         the brand file the intake recorded
A source is usable only when (a) it is a readable JSON object, (b) every palette value is
a #RRGGBB color (no CLIENT_MUST_SUPPLY / TREVOR_MUST_SUPPLY / name / blank), and (c) the
file belongs to this run's client: the file's brand_id equals intake.json brand_owner (names compared lowercase, letters and
digits only; containing is not matching).
The bundled BlackCEO file therefore resolves for BlackCEO's own pages and for nobody else.
Nothing else is a source: the skill keeps no prior-run or shared brand store, and SOP
section "Do not borrow one client's information" forbids carrying one over.

Unresolved means fail closed: `check` prints the sources tried and the client-facing ask
and exits 1; scripts/stage_gate.py (check, check-item, close) and
scripts/stage_executor.py refuse to start an image stage on that exit.

Usage:
  python3 scripts/brand_colors.py check  <run_dir>
  python3 scripts/brand_colors.py record <run_dir> --primary #HEX --text #HEX
      --background #HEX [--secondary #HEX] [--accent #HEX ...] [--background #HEX ...]
`record` writes the client's answer into the run's client brand file (created from
assets/brand/client-brand.template.json when the run has none) and points intake.json at it.
Exit codes: 0 resolved/recorded, 1 unresolved/refused, 2 usage.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
BUNDLED = SKILL_ROOT / "assets" / "brand" / "blackceo-brand.json"
TEMPLATE = SKILL_ROOT / "assets" / "brand" / "client-brand.template.json"
CLIENT_BRAND = "brand/client-brand.json"
# A path under private/ that never exists: callers that must hand a Path to a reader get
# an honest "unreadable" instead of another client's palette.
UNRESOLVED = "brand.UNRESOLVED"
# Every stage that wireframes, mockups or generates an image.
IMAGE_STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup",
                "image-inventory-prompts", "image-generation-qc", "final-mockups")

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
ASK = (
    "What are your brand colors? Please send: your main color, your second color, any "
    "accent colors, your background color or colors, and your text color. A color code "
    "like #1A2B3C is best; a brand guide or logo file works too and we will read the "
    "colors from it. Every wireframe and mockup will be made only in these colors."
)


def _json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _find(raw, run_dir):
    """Same order scripts/write_intake.py resolve_brand_file uses."""
    named = Path(raw)
    for cand in ([named] if named.is_absolute() else
                 [run_dir / named, named, SKILL_ROOT / named]):
        if cand.is_file():
            return cand
    return None


def _why_unusable(path, owner):
    """None when the brand file at `path` is a usable palette for `owner`, else the reason."""
    if path is None:
        return "file not found"
    brand = _json(path)
    if brand is None:
        return "not a readable JSON object"
    palette = brand.get("palette")
    if not isinstance(palette, dict) or not palette:
        return "declares no palette"
    bad = sorted(k for k, v in palette.items() if not (isinstance(v, str) and HEX.match(v)))
    if bad:
        return "client colors not supplied yet (not #RRGGBB: " + ", ".join(bad) + ")"
    b, o = _norm(brand.get("brand_id")), _norm(owner)
    if not o:
        return "intake.json has no brand_owner, so the palette cannot be tied to a client"
    if not b or b != o:
        return (f"palette belongs to brand_id {brand.get('brand_id')!r}, but this run is for "
                f"{owner!r}; another client's palette is never used")
    return None


class Resolution:
    def __init__(self, ok, source, path, brand, tried):
        self.ok, self.source, self.path, self.brand, self.tried = ok, source, path, brand, tried

    @property
    def palette(self):
        return dict((self.brand or {}).get("palette") or {})

    def block(self):
        """The line the wireframe and mockup prompts carry."""
        roles = (self.brand or {}).get("palette_roles")
        pairs = roles if isinstance(roles, dict) and roles else self.palette
        listed = "; ".join(f"{k} {', '.join(v) if isinstance(v, list) else v}"
                           for k, v in pairs.items())
        return ("BRAND COLORS — render this sheet only in the client's own brand colors: "
                f"{listed}. No other chromatic color; neutrals (white, black, grey) only "
                "for text and photo plates.")


def resolve(run_dir):
    run_dir = Path(run_dir)
    intake = _json(run_dir / "intake.json") or {}
    owner = intake.get("brand_owner")
    tried, cands = [], [("run brand pin private/brand.json", run_dir / "private" / "brand.json")]
    raw = intake.get("brand_file")
    if raw:
        cands.append((f"intake.json brand_file {raw!r}", _find(str(raw), run_dir)))
    else:
        tried.append("intake.json brand_file: not set (or no intake.json)")
    for label, path in cands:
        why = _why_unusable(path if path and Path(path).is_file() else None, owner)
        if why is None:
            return Resolution(True, label, Path(path), _json(path), tried)
        tried.append(f"{label}: {why}")
    return Resolution(False, None, None, None, tried)


def fallback_path(run_dir):
    """Path for callers that need *a* brand file when the intake names none: the bundled
    BlackCEO file for BlackCEO's own runs, else a path that never exists."""
    owner = (_json(Path(run_dir) / "intake.json") or {}).get("brand_owner")
    bundled = _json(BUNDLED) or {}
    if _norm(owner) and _norm(bundled.get("brand_id")) == _norm(owner):
        return BUNDLED
    return Path(run_dir) / "private" / UNRESOLVED


def brand_path(run_dir):
    """The one brand file every prompt, gate and QC check reads: the file of the palette
    `resolve` picked. Unresolved: BlackCEO's bundled file for BlackCEO's own run, else a path
    that never exists. No caller keeps its own pin/intake lookup, so none can disagree."""
    res = resolve(run_dir)
    return res.path if res.ok else fallback_path(run_dir)


def failure(run_dir, stage=None):
    """One refusal line when this stage may not start (None when colors are resolved or the
    stage makes no image)."""
    if stage is not None and stage not in IMAGE_STAGES:
        return None
    res = resolve(run_dir)
    if res.ok:
        return None
    return ("brand colors unresolved, no image stage may start. Tried: "
            + "; ".join(res.tried) + f". Ask the client: {ASK} Record the answer with "
            "scripts/brand_colors.py record.")


def _hex(value, role):
    text = str(value).strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        raise ValueError(f"{role}: {value!r} is not a color code; send #RRGGBB, not a color name")
    return "#" + text.upper()


def record(run_dir, primary, text, backgrounds, secondary=None, accents=()):
    run_dir = Path(run_dir)
    intake_path = run_dir / "intake.json"
    intake = _json(intake_path)
    if not intake or not intake.get("brand_owner"):
        raise ValueError("intake.json with a brand_owner must exist before colors are recorded")
    roles = {"primary": _hex(primary, "primary")}
    if secondary:
        roles["secondary"] = _hex(secondary, "secondary")
    if accents:
        roles["accent"] = [_hex(a, "accent") for a in accents]
    roles["background"] = [_hex(b, "background") for b in backgrounds]
    roles["text"] = _hex(text, "text")
    if not roles["background"]:
        raise ValueError("background: at least one background color is required")
    existing = _find(str(intake.get("brand_file") or ""), run_dir) if intake.get("brand_file") else None
    in_run = existing is not None and run_dir.resolve() in existing.resolve().parents
    target = existing if in_run else run_dir / CLIENT_BRAND
    brand = _json(target) if in_run else _json(TEMPLATE)
    if brand is None:
        raise ValueError(f"cannot read the brand file to update: {target}")
    # Slots gold/navy/cream are positional (accent-CTA, dark, light) in the brand-file form
    # shared with shared-utils; the five roles are kept verbatim in palette_roles.
    palette = {"gold": roles["primary"], "navy": roles["text"], "cream": roles["background"][0]}
    if secondary:
        palette["secondary"] = roles["secondary"]
    for i, a in enumerate(roles.get("accent", []), 1):
        palette[f"accent{i}"] = a
    for i, b in enumerate(roles["background"][1:], 2):
        palette[f"background{i}"] = b
    brand["palette"], brand["palette_roles"] = palette, roles
    brand.pop("_palette_note", None)
    slug = re.sub(r"[^a-z0-9]+", "-", str(intake["brand_owner"]).lower()).strip("-")
    brand["brand_id"] = slug or brand.get("brand_id")
    brand["source"] = f"client answer recorded {date.today().isoformat()} (brand_colors.py record)"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(brand, indent=2) + "\n", encoding="utf-8")
    if not in_run:
        intake["brand_file"] = CLIENT_BRAND
        intake_path.write_text(json.dumps(intake, indent=2) + "\n", encoding="utf-8")
    return target


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("run_dir", type=Path)
    r = sub.add_parser("record")
    r.add_argument("run_dir", type=Path)
    r.add_argument("--primary", required=True)
    r.add_argument("--secondary")
    r.add_argument("--accent", action="append", default=[])
    r.add_argument("--background", action="append", required=True)
    r.add_argument("--text", required=True)
    a = p.parse_args(argv)
    if not a.run_dir.is_dir():
        print(f"FAIL: run dir {a.run_dir} does not exist")
        return 2
    if a.cmd == "record":
        try:
            path = record(a.run_dir, a.primary, a.text, a.background, a.secondary, a.accent)
        except ValueError as exc:
            print(f"REFUSED: {exc}")
            return 1
        print(f"RECORDED brand colors in {path}")
    res = resolve(a.run_dir)
    if res.ok:
        print(f"BRAND_COLORS_RESOLVED source={res.source} file={res.path}")
        for name, value in res.palette.items():
            print(f"  {name} {value}")
        print(res.block())
        return 0
    print("BRAND_COLORS_MISSING; no wireframe, mockup or image stage may start. Sources tried:")
    for line in res.tried:
        print(f"  - {line}")
    print(f"ASK THE CLIENT: {ASK}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
