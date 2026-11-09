"""The shared pydeps contract: where the launch skills' Python packages live when pip refuses the interpreter.

A Homebrew or Debian Python is "externally managed" (PEP 668): plain pip and `pip --user` are refused, and
`--break-system-packages` is forbidden. `pip install --target <folder>` works, so the packages the launch
skills import (jsonschema) live in one versioned folder and every importer puts that folder on sys.path
itself, with no venv and no agent effort.

  folder   <root>/pydeps/py<major>.<minor>/      (versioned: a Python upgrade re-converges instead of
                                                  loading wheels built for another ABI)
  root     $OC_PYDEPS_DIR (the folder itself, used as-is) -> $OPENCLAW_ROOT -> /data/.openclaw when it
           exists (survives a Docker container recreate) -> $HOME/.openclaw
  lookup   the folder above, plus $HOME/.claude/pydeps/py<major>.<minor>/ (999 and claude-nine)

Names are exact because the 999 setup agent, the Command Center and lib-onboarding-state.sh
(oc_pydeps_dir, oc_pydeps_lookup) use the same contract. Stdlib only, so a vendored copy of the skill
works without shared-utils.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List


def tag() -> str:
    """'py3.14': the folder name for the running interpreter."""
    return "py%d.%d" % sys.version_info[:2]


def _root() -> Path:
    if os.environ.get("OPENCLAW_ROOT"):
        return Path(os.environ["OPENCLAW_ROOT"])
    if os.path.isdir("/data/.openclaw"):
        return Path("/data/.openclaw")
    return Path.home() / ".openclaw"


def install_dir() -> Path:
    """Where `pip install --target` puts a package for this interpreter."""
    if os.environ.get("OC_PYDEPS_DIR"):
        return Path(os.environ["OC_PYDEPS_DIR"])
    return _root() / "pydeps" / tag()


def lookup_dirs() -> List[Path]:
    """Every pydeps folder that exists for this interpreter, best first."""
    if os.environ.get("OC_PYDEPS_DIR"):
        candidates = [Path(os.environ["OC_PYDEPS_DIR"])]
    else:
        candidates = [_root() / "pydeps" / tag(), Path.home() / ".claude" / "pydeps" / tag()]
    return [d for d in candidates if d.is_dir()]


def activate() -> List[str]:
    """Put the existing pydeps folders at the front of sys.path (idempotent); return the ones added."""
    added = [str(d) for d in lookup_dirs() if str(d) not in sys.path]
    sys.path[:0] = added
    return added
