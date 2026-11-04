"""The environment for a test that starts the launcher in a CHILD interpreter, so it can neither read nor change
a real pydeps folder and can never reach a package index.

Why this exists: importing `launcher_core` puts the shared pydeps folder AHEAD of PYTHONPATH on sys.path, so a
test that shadows jsonschema (or attrs) with a stub on PYTHONPATH is silently overridden on any box that has
the pydeps folder. And the CLI repairs a missing package itself (dependencies.ensure_runtime_packages), so on a
box with network the same test would pip-install into the real $HOME/.openclaw/pydeps. A test that simulates a
missing package must therefore:

  * point OC_PYDEPS_DIR (the folder itself, used as-is) at an EMPTY temp folder, so nothing real is activated
    and any install lands in a temp dir;
  * set PIP_NO_INDEX so pip cannot reach a package index (an attempted repair fails fast and offline);
  * set HOME to the temp folder, so the child can never read or write the real home folder (its user
    site-packages included: the real jsonschema reaches it through PYTHONPATH, below);
  * hand the child the real jsonschema through PYTHONPATH AFTER its stub, so the control run (no stub) still
    finds the package wherever this process got it (site-packages, user site, or a pydeps folder), and a stub
    placed before it still wins.

Stdlib only.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Tuple


def real_jsonschema_home() -> str:
    """The folder this process imports jsonschema from: the one place the child must be able to find it."""
    import jsonschema

    return str(Path(jsonschema.__file__).resolve().parent.parent)


def hermetic_env(tmp_root: Path, *front_paths: str) -> Tuple[Dict[str, str], Path]:
    """(env, empty_pydeps_folder) for a child launcher process. front_paths go first on PYTHONPATH (the stubs)."""
    pydeps = Path(tmp_root) / "empty-pydeps"
    pydeps.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PIP_") and k != "OPENCLAW_ROOT"}
    env.update(OC_PYDEPS_DIR=str(pydeps), PIP_NO_INDEX="1", PIP_NO_CACHE_DIR="1",
               PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_CONFIG_FILE=os.devnull,
               LAUNCH_EVENTS_SPOOL=str(Path(tmp_root) / "events-spool"),  # launch events never spool into $HOME
               HOME=str(tmp_root))  # and nothing else the child does with $HOME can reach the real one
    parts = [*front_paths, real_jsonschema_home()]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env, pydeps
