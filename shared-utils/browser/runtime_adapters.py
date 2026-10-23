"""Browser-harness runtime adapters (W3C): platform, dependency, writable-path
and headless policy for automation-owned browser work on Mac and VPS.

Scope (GHL-DELIVERY-SPEC.md, stream W3, assignment W3C):

  * OS / architecture / dependency detection — probe and report, never assume.
  * Writable scratch / profile / artifact paths — verified by a real write
    probe, unit-prefixed, platform-correct.
  * No Mac paths on Linux: ``assert_paths_platform_safe`` refuses them at the
    choke point every harness path passes through.
  * No assumed display: headless is ALWAYS required for automation-owned
    browsers (spec: "HEADLESS on Mac and VPS"). ``display_state`` is
    diagnostics only and never relaxes that.

Stdlib only. Import from a sibling checkout:

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from runtime_adapters import detect_platform, harness_paths, headless_required

Self-check: ``python3 runtime_adapters.py`` runs offline assert-based checks.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

# macOS-only absolute roots. A Linux harness must never be handed one of these.
MAC_ONLY_ROOTS = ("/Users/", "/Volumes/", "/Applications/", "/Library/")


class PathPlatformError(ValueError):
    """A path violates the host platform's layout rules (e.g. Mac path on Linux)."""


class DependencyError(RuntimeError):
    """A required runtime dependency is missing; names each one."""


@dataclass(frozen=True)
class PlatformInfo:
    """Normalized host facts. ``system`` is one of darwin/linux/windows/other;
    ``arch`` is one of arm64/x86_64/other."""

    system: str
    arch: str
    python: str
    is_mac: bool
    is_linux: bool
    is_vps: bool  # linux host that looks like a VPS/container deployment


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    found: bool
    detail: str


@dataclass(frozen=True)
class HarnessPaths:
    base_dir: Path
    scratch_dir: Path
    profile_dir: Path
    artifact_dir: Path
    prefix: str


class DisplayState:
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"
    ALL = (PRESENT, ABSENT, UNKNOWN)


def detect_platform() -> PlatformInfo:
    """Detect OS, architecture and VPS/container shape from live probes."""
    if sys.platform.startswith("linux"):
        system = "linux"
    elif sys.platform == "darwin":
        system = "darwin"
    elif sys.platform in ("win32", "cygwin"):
        system = "windows"
    else:
        system = "other"
    machine = os.uname().machine.lower() if hasattr(os, "uname") else ""
    if machine in ("arm64", "aarch64"):
        arch = "arm64"
    elif machine in ("x86_64", "amd64"):
        arch = "x86_64"
    else:
        arch = "other"
    is_linux = system == "linux"
    # VPS/container markers: /data/.openclaw (Hostinger Docker, see
    # detect_platform.py) or a Docker container boundary.
    is_vps = is_linux and (
        Path("/data/.openclaw").exists() or Path("/.dockerenv").exists()
    )
    return PlatformInfo(
        system=system,
        arch=arch,
        python=".".join(str(p) for p in sys.version_info[:3]),
        is_mac=system == "darwin",
        is_linux=is_linux,
        is_vps=is_vps,
    )


def _playwright_browser_roots(env: Mapping[str, str]) -> List[Path]:
    override = env.get("PLAYWRIGHT_BROWSERS_PATH")
    if override:
        return [Path(override)]
    home = Path.home()
    return [
        home / "Library/Caches/ms-playwright",  # darwin
        home / ".cache/ms-playwright",  # linux
        home / "AppData/Local/ms-playwright",  # windows
    ]


def detect_dependencies(env: Optional[Mapping[str, str]] = None) -> dict:
    """Probe runtime dependencies. Missing ones are reported, never raised."""
    env = os.environ if env is None else env
    statuses: dict = {}

    py_ok = sys.version_info >= (3, 9)
    statuses["python"] = DependencyStatus(
        "python", py_ok, "interpreter %s (>=3.9 required)" % detect_platform().python
    )

    import importlib.util

    spec = importlib.util.find_spec("playwright")
    statuses["playwright"] = DependencyStatus(
        "playwright",
        spec is not None,
        "python module importable" if spec else "python module missing",
    )

    cli = shutil.which("playwright")
    statuses["playwright_cli"] = DependencyStatus(
        "playwright_cli", cli is not None, cli or "no playwright executable on PATH"
    )

    chromium_detail = "no playwright browser root present"
    chromium_found = False
    for root in _playwright_browser_roots(env):
        if root.is_dir() and any(root.glob("chromium*")):
            chromium_found = True
            chromium_detail = "chromium build under %s" % root
            break
        if root.is_dir():
            chromium_detail = "browser root %s has no chromium build" % root
    statuses["chromium"] = DependencyStatus("chromium", chromium_found, chromium_detail)

    node = shutil.which("node")
    statuses["node"] = DependencyStatus(
        "node", node is not None, node or "no node on PATH"
    )

    git = shutil.which("git")
    statuses["git"] = DependencyStatus("git", git is not None, git or "no git on PATH")

    return statuses


def assert_dependencies(statuses: Mapping[str, DependencyStatus],
                        required: Sequence[str]) -> None:
    """Raise DependencyError naming every missing required dependency."""
    missing = [n for n in required if not statuses.get(n, DependencyStatus(n, False, "not probed")).found]
    if missing:
        raise DependencyError("missing dependencies: %s" % ", ".join(missing))


def looks_like_mac_path(path) -> bool:
    """True when the path sits under a macOS-only absolute root."""
    return str(path).startswith(MAC_ONLY_ROOTS)


def assert_paths_platform_safe(paths: Sequence, info: PlatformInfo) -> None:
    """Refuse Mac-only paths on Linux. The single choke point every harness
    path passes through before use."""
    for p in paths:
        text = str(p)
        if info.is_linux and text.startswith(MAC_ONLY_ROOTS):
            raise PathPlatformError(
                "mac path %r is not valid on linux" % text
            )


def _writable_dir(candidates: Sequence[Path]) -> Optional[Path]:
    """First candidate that can actually be created and written to."""
    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / (".write-probe-%d" % os.getpid())
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            continue
        return cand
    return None


def scratch_candidates(unit_id: str, info: PlatformInfo,
                       box_slug: Optional[str] = None,
                       env: Optional[Mapping[str, str]] = None) -> List[Path]:
    """Ordered base-dir candidates: explicit override, then platform temp."""
    env = os.environ if env is None else env
    prefix = "%s-%s-" % (box_slug, unit_id) if box_slug else "%s-" % unit_id
    out: List[Path] = []
    override = env.get("GHL_HARNESS_SCRATCH")
    if override:
        # Override is the ROOT; the prefixed dir is still created under it so
        # every harness dir carries the <box-slug>-<unit-id>- attribution.
        out.append(Path(override) / prefix)
    for key in ("TMPDIR", "TMP", "TEMP"):
        val = env.get(key)
        if val:
            out.append(Path(val) / prefix)
            break
    out.append(Path(tempfile.gettempdir()) / prefix)
    if info.is_linux:
        out.append(Path("/tmp") / prefix)
    deduped: List[Path] = []
    for cand in out:
        if cand not in deduped:
            deduped.append(cand)
    return deduped


def harness_paths(unit_id: str, box_slug: Optional[str] = None,
                  env: Optional[Mapping[str, str]] = None) -> HarnessPaths:
    """Resolve verified-writable scratch/profile/artifact dirs for a unit.

    Every candidate is platform-checked (no Mac paths on Linux) BEFORE any
    filesystem probe. The chosen base dir is prefixed ``<box-slug>-<unit-id>-``
    so lane temp files stay attributable and removable.
    """
    info = detect_platform()
    env = os.environ if env is None else env
    prefix = "%s-%s-" % (box_slug, unit_id) if box_slug else "%s-" % unit_id
    candidates = scratch_candidates(unit_id, info, box_slug=box_slug, env=env)
    assert_paths_platform_safe(candidates, info)
    base = _writable_dir(candidates)
    if base is None:
        raise PathPlatformError(
            "no writable harness dir among: %s"
            % ", ".join(str(c) for c in candidates)
        )
    profile = base / "profile"
    artifact = base / "artifacts"
    for sub in (profile, artifact):
        sub.mkdir(parents=True, exist_ok=True)
    paths = HarnessPaths(
        base_dir=base, scratch_dir=base, profile_dir=profile,
        artifact_dir=artifact, prefix=prefix,
    )
    assert_paths_platform_safe(
        [paths.base_dir, paths.scratch_dir, paths.profile_dir, paths.artifact_dir],
        info,
    )
    return paths


def display_state(info: Optional[PlatformInfo] = None,
                  env: Optional[Mapping[str, str]] = None) -> str:
    """Diagnostics only: whether the session shows a display.

    NEVER gates browser headlessness — automation-owned browsers run headless
    on Mac and VPS regardless of what this returns.
    """
    info = detect_platform() if info is None else info
    env = os.environ if env is None else env
    if info.is_mac or info.system == "windows":
        return DisplayState.PRESENT
    if info.is_linux:
        if env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"):
            return DisplayState.PRESENT
        return DisplayState.ABSENT
    return DisplayState.UNKNOWN


def headless_required() -> bool:
    """Always True. GHL-DELIVERY-SPEC.md browser policy: automation-owned
    browser work is HEADLESS on Mac and VPS. No display may relax this."""
    return True


_REDACT_RE = re.compile(
    r"""(?ix)
        (?P<sk>\bsk-[A-Za-z0-9_\-]{6,}\b)
      | (?P<bearer>\bbearer[ \t]+[A-Za-z0-9._\-]{6,})
      | (?P<kv>\b(?:api[_-]?key|apikey|access[_-]?token|token|secret|password|passwd|auth)
          [ \t]*[=:][ \t]*)[^\s'"&]+
    """
)


def redact(text: str) -> str:
    """Mask secret-shaped values before anything is logged or echoed."""

    def _sub(match: "re.Match") -> str:
        if match.group("sk"):
            return "sk-***"
        if match.group("bearer"):
            return "bearer ***"
        return match.group("kv") + "***"

    return _REDACT_RE.sub(_sub, text)


def _self_check() -> None:
    info = detect_platform()
    assert info.system in ("darwin", "linux", "windows", "other"), info
    assert info.arch in ("arm64", "x86_64", "other"), info
    assert info.is_mac == (info.system == "darwin"), info
    assert info.is_linux == (info.system == "linux"), info

    deps = detect_dependencies()
    assert set(deps) >= {"python", "playwright", "chromium", "node", "git"}, deps
    assert deps["python"].found, deps["python"]
    for st in deps.values():
        assert st.detail, st

    assert looks_like_mac_path("/Users/someone/file")
    assert looks_like_mac_path("/Volumes/USB/x")
    assert not looks_like_mac_path("/tmp/x")
    assert not looks_like_mac_path("/home/linux/x")

    linux = PlatformInfo("linux", "x86_64", "3.11.0", False, True, True)
    try:
        assert_paths_platform_safe(["/Users/leak/profile"], linux)
    except PathPlatformError:
        pass
    else:
        raise AssertionError("mac path accepted on linux")
    assert_paths_platform_safe(["/tmp/ok", "/home/ok"], linux)
    mac = PlatformInfo("darwin", "arm64", "3.11.0", True, False, False)
    assert_paths_platform_safe(["/Users/ok"], mac)

    hp = harness_paths("W3C-U1", box_slug="mac-mini-m4")
    for d in (hp.base_dir, hp.scratch_dir, hp.profile_dir, hp.artifact_dir):
        assert d.is_dir() and os.access(d, os.W_OK), d
        assert not str(d).startswith(MAC_ONLY_ROOTS) or info.is_mac, d
    assert hp.base_dir.name.startswith("mac-mini-m4-W3C-U1-"), hp.base_dir

    assert headless_required() is True
    assert display_state(info) in DisplayState.ALL

    secret_text = "sk-abcdef1234567890 Authorization: Bearer ghi987654321 api_key=zzzTOPSECRET"
    masked = redact(secret_text)
    assert "abcdef1234567890" not in masked, masked
    assert "ghi987654321" not in masked, masked
    assert "zzzTOPSECRET" not in masked, masked
    assert redact("plain text stays") == "plain text stays"

    print("runtime_adapters self-check OK")


if __name__ == "__main__":
    _self_check()
