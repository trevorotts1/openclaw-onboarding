"""SPF019 test helper: the minimal intake that gives a fixture run resolved client brand colors.

BlackCEO's own page resolves from the bundled brand file; any other client needs its own palette.
"""
import json
from pathlib import Path

BLACKCEO_INTAKE = {"brand_owner": "blackceo", "brand_file": "assets/brand/blackceo-brand.json"}


def give_blackceo_colors(run_dir):
    """Merge BlackCEO's intake brand fields into <run_dir>/intake.json (created if absent)."""
    path = Path(run_dir) / "intake.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.update(BLACKCEO_INTAKE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
