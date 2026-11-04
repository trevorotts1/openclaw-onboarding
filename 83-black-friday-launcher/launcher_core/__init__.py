"""Black Friday Launcher core (working skill number in constants.py)."""

from . import pydeps

# Before any module here (or the Skill 79 validator it loads) imports jsonschema: put the shared pydeps
# folder on sys.path, so a plain `python3 -m launcher_core.cli ...` works on a box whose Python refuses pip.
pydeps.activate()

from .constants import SKILL_DIR_NAME, SKILL_NAME, SKILL_NUMBER, SKILL_VERSION  # noqa: E402

__all__ = ["SKILL_DIR_NAME", "SKILL_NAME", "SKILL_NUMBER", "SKILL_VERSION"]
