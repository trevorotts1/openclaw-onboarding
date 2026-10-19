"""Test double for scripts/brand_colors.py (the brand-color resolution contract).

Mirrors only the surface scripts/design_board.py consumes: resolve(run_dir) -> object with
ok, source, path, brand, palette, tried, block(); failure(run_dir, stage=None) -> str|None.
Where the real module is installed beside the scripts it shadows this one, and the board
fixtures satisfy both (intake brand_owner matches the brand file's brand_id, #RRGGBB palette).
"""
import json
import re
from pathlib import Path

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class Resolution:
    def __init__(self, ok, source, path, brand, tried):
        self.ok, self.source, self.path, self.brand, self.tried = ok, source, path, brand, tried

    @property
    def palette(self):
        return dict((self.brand or {}).get("palette") or {})

    def block(self):
        return "BRAND COLORS " + "; ".join(f"{k} {v}" for k, v in self.palette.items())


def resolve(run_dir):
    run_dir = Path(run_dir)
    try:
        intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
        brand = json.loads((run_dir / intake["brand_file"]).read_text(encoding="utf-8"))
        palette = brand["palette"]
    except (OSError, ValueError, KeyError, TypeError):
        return Resolution(False, None, None, None, ["no readable brand file"])
    if not palette or not all(isinstance(v, str) and HEX.match(v) for v in palette.values()):
        return Resolution(False, None, None, None, ["palette values are not #RRGGBB"])
    return Resolution(True, "intake brand_file", run_dir / intake["brand_file"], brand, [])


def failure(run_dir, stage=None):
    res = resolve(run_dir)
    return None if res.ok else "brand colors unresolved. Tried: " + "; ".join(res.tried)
