#!/usr/bin/env python3
"""oc_python.py: the Python mirror of the ONE-PYTHON resolver in platform/common.sh.

Python code that creates a venv or installs a package uses this module instead
of trusting PATH or a Homebrew interpreter. Same rules as the shell resolver
(oc_python / oc_venv in platform/common.sh, the single source of truth):

  * OC_PYTHON (env) wins when executable; on Linux it is refused when it is a
    Homebrew/Linuxbrew python.
  * Linux (VPS / Docker / Contabo): realpath of /usr/bin/python3, then the
    <openclaw root>/.oc-python stamp, then the first NON-Homebrew python3 on PATH.
  * macOS: the python3 on PATH (unchanged Mac behaviour).

A venv is created with ``uv venv --python <base> --seed`` when uv exists (Debian's
3.13 has no ensurepip, so ``-m venv`` makes a hollow venv there), else with
``<base> -m venv`` when ensurepip exists.

    python3 shared-utils/oc_python.py            # prints the canonical interpreter
"""
from __future__ import annotations

import os
import platform as _platform
import shutil
import subprocess
import sys

SYSTEM_PYTHON = "/usr/bin/python3"
_HOMEBREW_MARKERS = ("linuxbrew", "/Homebrew/", "/homebrew/", "/Cellar/", "/opt/python@")


def is_homebrew(path: str) -> bool:
    if not path:
        return False
    real = os.path.realpath(path)
    return any(m in path or m in real for m in _HOMEBREW_MARKERS)


def _is_linux() -> bool:
    return _platform.system() == "Linux"


def openclaw_root() -> str:
    root = os.environ.get("OPENCLAW_ROOT") or os.environ.get("OC_ROOT") or os.environ.get("OC_CONFIG")
    if not root:
        root = os.path.expanduser("~/.openclaw")
        if _is_linux() and os.path.isdir("/data/.openclaw") and not os.path.isdir(root):
            root = "/data/.openclaw"
    return root.rstrip("/")


def stamp_read() -> str | None:
    try:
        with open(os.path.join(openclaw_root(), ".oc-python")) as fh:
            value = fh.readline().strip()
    except OSError:
        return None
    return value or None


def _executable(p: str | None) -> bool:
    return bool(p) and os.path.isfile(p) and os.access(p, os.X_OK)


def canonical_python() -> str | None:
    """The ONE interpreter for installs and venvs on this box (None if none)."""
    linux = _is_linux()
    forced = os.environ.get("OC_PYTHON")
    if _executable(forced) and not (linux and is_homebrew(forced)):
        return forced
    if not linux:
        return shutil.which("python3")
    system = os.environ.get("_OC_PY_SYSTEM", SYSTEM_PYTHON)
    if _executable(system):
        real = os.path.realpath(system)
        real = real if _executable(real) else system
        if not is_homebrew(real):
            return real
    stamped = stamp_read()
    if _executable(stamped) and not is_homebrew(stamped):
        return stamped
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(d, "python3") if d else ""
        if _executable(cand) and not is_homebrew(cand):
            return cand
    return None


def venv_base_python(launching: str | None = None) -> str:
    """The interpreter a new venv is built on: the launching interpreter, except
    a Homebrew python on Linux, which is swapped for the canonical one."""
    launching = launching or sys.executable
    if _is_linux() and is_homebrew(launching):
        return canonical_python() or launching
    return launching


def uv_binary() -> str | None:
    home = os.path.expanduser("~")
    for c in (shutil.which("uv"), os.path.join(home, ".local/bin/uv"), "/data/.local/bin/uv",
              "/data/linuxbrew/.linuxbrew/bin/uv", "/home/linuxbrew/.linuxbrew/bin/uv",
              "/opt/homebrew/bin/uv", "/usr/local/bin/uv", os.path.join(home, ".cargo/bin/uv")):
        if _executable(c):
            return c
    return None


def has_ensurepip(py: str) -> bool:
    try:
        return subprocess.run([py, "-c", "import ensurepip"], capture_output=True,
                              timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def venv_create_argvs(base: str, env_dir: str) -> list[list[str]]:
    """Ordered venv-creation attempts on <base>: ``-m venv`` only when ensurepip
    exists, then ``uv venv --seed`` (ensurepip-free). Never a PATH python."""
    out = []
    if has_ensurepip(base):
        out.append([base, "-m", "venv", env_dir])
    uv = uv_binary()
    if uv:
        out.append([uv, "venv", "--python", base, "--seed", "--allow-existing", env_dir])
    return out


if __name__ == "__main__":
    py = canonical_python()
    if not py:
        print("one-python: no non-Homebrew python3 found", file=sys.stderr)
        sys.exit(1)
    print(py)
