#!/usr/bin/env python3
"""G-6 (fix plan A1, unowned): Skill 71's policy READS the owner cap, never hard-codes it.

FAILS before the change: the gpt-image-2-6 row carried `"max_chars": 20000`, a second
copy of the number that produced the 32,000 drift. PASSES after: the row names the
owner catalog row and `prompt_budget()` resolves the value from 66-kie-image/models.json.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL71 = ROOT / "71-blackceo-signature-page"


def load_executor():
    spec = importlib.util.spec_from_file_location(
        "se_g6", SKILL71 / "scripts" / "stage_executor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    fails = []

    policy = json.loads((SKILL71 / "references" / "prompt-budget-policy.json")
                        .read_text(encoding="utf-8"))
    rows = [r for r in policy.get("models") or []
            if isinstance(r, dict) and "gpt-image-2-6" in str(r.get("match"))]
    if not rows:
        fails.append("policy has no gpt-image-2-6 row")
    for row in rows:
        if "max_chars" in row:
            fails.append("policy row hard-codes max_chars=%r instead of reading the owner cap"
                         % row["max_chars"])
        if not isinstance(row.get("max_chars_from"), dict):
            fails.append("policy row has no max_chars_from block naming the owner catalog")

    se = load_executor()
    got = se.prompt_budget("gpt-image-2-6/sunburst-text-to-image")
    if not got or got.get("max_chars") != 20000:
        fails.append("prompt_budget did not resolve the owner cap 20000: %r" % (got,))
    elif "models.json" not in str(got.get("source")):
        fails.append("prompt_budget source does not name the owner catalog: %r"
                     % got.get("source"))

    # The decisive test: change the ONE source and the band must follow it. A hard-coded
    # 20,000 cannot pass this.
    tmp = Path(tempfile.mkdtemp(prefix="bld002-g6-"))
    try:
        (tmp / "71-blackceo-signature-page" / "references").mkdir(parents=True)
        (tmp / "66-kie-image").mkdir(parents=True)
        shutil.copy(SKILL71 / "references" / "prompt-budget-policy.json",
                    tmp / "71-blackceo-signature-page" / "references" / "prompt-budget-policy.json")
        models = json.loads((ROOT / "66-kie-image" / "models.json").read_text(encoding="utf-8"))
        for row in models["models"]:
            if str(row.get("canonical_model_id", "")).startswith("gpt-image-2-6/"):
                row["owner_prompt_cap_chars"] = 18000
        (tmp / "66-kie-image" / "models.json").write_text(json.dumps(models), encoding="utf-8")
        se.SKILL_ROOT = tmp / "71-blackceo-signature-page"
        moved = se.prompt_budget("gpt-image-2-6/sunburst-text-to-image")
        if not moved or moved.get("max_chars") != 18000:
            fails.append("prompt_budget ignored the owner catalog (expected 18000, got %r)" % (moved,))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for f in fails:
        print("FAIL G-6: " + f)
    if fails:
        return 1
    print("PASS G-6: policy reads owner_prompt_cap_chars from 66-kie-image/models.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
