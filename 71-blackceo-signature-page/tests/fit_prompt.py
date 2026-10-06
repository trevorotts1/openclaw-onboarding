"""Test helper: grow a hand-authored fixture prompt into the KIE rule 12 band for the default image model.

The fixtures under tests/fixtures are small on purpose. The length gate now measures 95 to 100 percent of the model
maxLength (shared enforcer, Skill 74 prompt-budget), so a test that needs a PASSING prompt appends distinct
art-direction sentences (never one repeated line, so the padding rule stays satisfied) up to the middle of the band."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_prompt as vp  # noqa: E402

_SYL = ["ba", "ko", "ri", "mu", "te", "sa", "no", "vi", "la", "pe", "do", "xu", "fi", "ga", "hu", "ze"]


def _word(i):
    a, b, c = i % 16, (i // 16) % 16, (i // 256) % 16
    return _SYL[a] + _SYL[b] + _SYL[c] + "n"


def band_target(model=vp.IMAGE_MODEL_DEFAULT):
    b = vp.KPE.budget_for(model)
    return (b["target_min"] + b["max"]) // 2


def fit_text(text, model=vp.IMAGE_MODEL_DEFAULT):
    out = text.rstrip() + "\n\nADDITIONAL DIRECTION FOR THIS PAGE:\n"
    goal, i = band_target(model), 0
    while len(out) < goal:
        words = " ".join(_word(i * 7 + k) for k in range(9))
        out += "Detail %d keeps %s clear and intentional for the reader. " % (i, words)
        i += 1
    return out


def fit_file(src, dest):
    Path(dest).write_text(fit_text(Path(src).read_text(encoding="utf-8")), encoding="utf-8")
    return str(dest)
