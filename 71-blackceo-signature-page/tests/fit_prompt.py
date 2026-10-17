"""Grow fixture prompts into the KIE rule 12 length band (95 to 100
percent of the model maximum, hard floor 80 percent) adopted as
Skill 71's native authoring target by owner Decision 1 (2026-10-15).

TEST MACHINERY ONLY. The filler is synthetic: deterministic unique
generated sentences inserted into the Negative block before its
Do-not statements, sized to 97 percent of the policy maximum for the
model. This helper exists so the suite's fixtures, which are small
on purpose, can pass the same prompt-stage band check a production
prompt must pass. It is NOT a production authoring method and must
never be used to bring a real prompt into the band: production
prompts reach the band by genuine specification only, and padding
a production prompt is a named failure in validate_prompt.py.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_prompt as vp  # noqa: E402,F401

_SYL = ["ba", "ko", "ri", "mu", "te", "sa", "no", "vi",
        "la", "pe", "do", "xu", "fi", "ga", "hu", "ze"]


def _gword(n):
    a, b, c = n % 16, (n // 16) % 16, (n // 256) % 16
    return _SYL[a] + _SYL[b] + _SYL[c] + "n"


def _target_chars(model):
    """97 percent of the policy maximum for the model, or None when
    no character maximum is recorded (nothing to fit to)."""
    cap = vp.cap_for_model(model or vp.IMAGE_MODEL_DEFAULT, vp.load_policy())
    if cap.get("unit") != "chars" or not cap.get("max_chars"):
        return None
    return int(cap["max_chars"] * 97 / 100)


def fit_text(text, model=None):
    target = _target_chars(model)
    if target is None:
        return text
    # Characters are counted the validator's way (NFC, trimmed) and
    # the growth is inserted mid-text, so aim the raw length at the
    # target plus the text's own leading/trailing whitespace.
    raw_target = target + (len(text) - len(text.strip()))
    neg = text.upper().find("NEGATIVE BLOCK")
    anchor_at = text.find("\nDo not", neg if neg >= 0 else 0)
    if anchor_at == -1:
        return text
    head, tail = text[:anchor_at], text[anchor_at:]
    i = 0
    while len(head) + len(tail) < raw_target:
        ws = [_gword(i * 10 + k) for k in range(10)]
        sentence = (f"Beat {i}: the {ws[0]} {ws[1]} beside the {ws[2]} keeps "
                    f"the {ws[3]} light specific to scene {i}, with {ws[4]} "
                    f"shadow, {ws[5]} air, {ws[6]} texture on the {ws[7]} "
                    f"wall, and {ws[8]} {ws[9]} detail.\n")
        room = raw_target - (len(head) + len(tail))
        if len(sentence) > room:
            filler = f"Beat {i}: " + " ".join(_gword(i * 10 + k)
                                              for k in range(60))
            head += (filler[:room - 1] + "\n") if room > 1 else filler[:room]
            break
        head += sentence
        i += 1
    return head + tail


def fit_file(src, dest):
    Path(dest).write_text(fit_text(Path(src).read_text(encoding="utf-8")),
                          encoding="utf-8")
    return str(dest)
