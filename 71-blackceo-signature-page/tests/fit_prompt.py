"""RETIRED (Amendment 6, Part C): this helper grew fixture prompts into
the KIE rule 12 length band (95 to 100 percent of the model maximum,
hard floor 80 percent) that the shared enforcer used to impose.

That band is withdrawn inside Skill 71. Element completeness governs
prompt acceptance now; length is telemetry only, and no fixture needs
to be fitted to a band. fit_text is kept as an identity function so any
stale import fails loudly in review rather than silently padding a
prompt: it returns the text unchanged, because there is nothing left
to fit to.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_prompt as vp  # noqa: E402,F401


def fit_text(text, model=None):
    return text


def fit_file(src, dest):
    Path(dest).write_text(fit_text(Path(src).read_text(encoding="utf-8")),
                          encoding="utf-8")
    return str(dest)
