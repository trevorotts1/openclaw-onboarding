"""Resolve presentation runtime paths within one selected client installation.

Explicit root/workspace pins win. Native Linux defaults to HOME/.openclaw;
/data is selected only for an existing Linux installation or a mounted container.
mac/vps overrides remain usable for platform simulation, but never add credential
fallbacks from another installation. PRESENTATION_OC_PATHS=0 cannot bypass this
client boundary. This module reads paths/configuration, never secret values.
"""
from __future__ import annotations

import json
import os
import platform
import re
from pathlib import Path
from typing import List, Mapping, Optional

FLAG_ENV = "PRESENTATION_OC_PATHS"
PLATFORM_ENV = "OPENCLAW_PLATFORM"
VPS_ROOT = Path("/data/.openclaw")


def _platform(view: Optional[Mapping[str, str]] = None) -> str:
    view = os.environ if view is None else view
    raw = view.get(PLATFORM_ENV, "")
    if raw:
        if raw not in ("mac", "vps"):
            raise ValueError("Invalid OPENCLAW_PLATFORM")
        return raw
    detected = platform.system()
    if detected not in ("Darwin", "Linux"):
        raise ValueError("Unsupported presentation runtime OS")
    return "mac" if detected == "Darwin" else "vps"


def _container() -> bool:
    if Path("/.dockerenv").is_file() or Path("/run/.containerenv").is_file():
        return True
    try:
        return bool(re.search(r"(^|/)(docker|kubepods|libpod)(/|[-.])", Path("/proc/1/cgroup").read_text(), re.M))
    except OSError:
        return False


def _absolute(value: str, name: str) -> Path:
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        raise ValueError(f"Invalid {name}")
    path = Path(value)
    if not path.is_absolute() or path == Path("/"):
        raise ValueError(f"{name} must be an absolute non-root path")
    return path


def _pins(view: Mapping[str, str], names: tuple) -> Optional[Path]:
    pins = [_absolute(view[name], name) for name in names if view.get(name)]
    if pins and any(p.resolve() != pins[0].resolve() for p in pins[1:]):
        raise ValueError("Conflicting client path pins: " + ", ".join(names))
    return pins[0] if pins else None


def root(environ: Optional[Mapping[str, str]] = None) -> Path:
    view = os.environ if environ is None else environ
    selected = _pins(view, ("OPENCLAW_ROOT", "OC_ROOT", "OC_CONFIG"))
    plat = _platform(view)
    if selected is not None:
        return selected
    home = _absolute(view.get("HOME", str(Path.home())), "HOME") / ".openclaw"
    if plat == "vps":
        if VPS_ROOT.is_dir():
            if home.is_dir() and home.resolve() != VPS_ROOT.resolve():
                raise ValueError("Two client roots exist; set OPENCLAW_ROOT")
            return VPS_ROOT
        if _container() and VPS_ROOT.parent.is_dir() and not home.is_dir():
            return VPS_ROOT
    return home


def workspace(environ: Optional[Mapping[str, str]] = None) -> Path:
    view = os.environ if environ is None else environ
    selected_root = root(view)
    selected = _pins(view, ("OPENCLAW_WORKSPACE_PATH", "OPENCLAW_WORKSPACE_ROOT"))
    if selected is not None:
        return selected
    config = selected_root / "openclaw.json"
    if config.exists():
        try:
            data = json.loads(config.read_text())
            configured = data.get("agents", {}).get("defaults", {}).get("workspace")
        except (OSError, ValueError, AttributeError) as exc:
            raise ValueError("Cannot read the selected client workspace configuration") from exc
        if configured is not None and configured != "":
            if isinstance(configured, str) and configured.startswith("~/"):
                configured = str(_absolute(view.get("HOME", str(Path.home())), "HOME") / configured[2:])
            return _absolute(configured, "configured workspace")
    return selected_root / "workspace"


def _within(path: Path, boundaries: tuple) -> Path:
    resolved = path.resolve()
    if not any(resolved == base.resolve() or base.resolve() in resolved.parents for base in boundaries):
        raise ValueError("Path escapes the selected client installation/workspace")
    return path


def skills() -> Path:
    selected_root = root()
    override = os.environ.get("OC_SKILLS_DIR", "")
    return _within(_absolute(override, "OC_SKILLS_DIR"), (selected_root,)) if override else selected_root / "skills"


def state_dir() -> Path:
    return root() / "state" / "presentation"


def secrets_env_candidates(environ: Optional[Mapping[str, str]] = None) -> List[Path]:
    view = os.environ if environ is None else environ
    selected_root, selected_workspace = root(view), workspace(view)
    boundaries = (selected_root, selected_workspace)
    candidates = []
    override = view.get("OPENCLAW_SECRETS", "")
    if override:
        candidates.append(_within(_absolute(override, "OPENCLAW_SECRETS"), boundaries))
    candidates.extend((selected_root / "secrets/.env", selected_root / "secrets/secrets.env",
                       selected_root / ".env", selected_workspace / ".env"))
    # Resolve symlinks before returning any candidate: a link to another client's
    # store is not permission to borrow credentials, even at a standard filename.
    return list(dict.fromkeys(_within(path, boundaries) for path in candidates))
