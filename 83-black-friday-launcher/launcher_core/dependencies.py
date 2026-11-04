"""Dependency package for enabling the Launcher in 999.

Reads the manifest and reports, per entry, whether it is PRESENT in this
repository, MISSING, or UNVERIFIABLE, with the evidence used. It writes nothing
outside this skill. `enabled_in_999` in the report is true only when the skill's
own registration.json records the enablement AND no required entry is
missing, so the flag is evidence-derived, never hard-coded.

A missing entry is a finding, not a crash; `check()` exits 0 whenever the
manifest itself is readable, so the report can be run at any time.
"""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import pydeps
from .constants import (REPO_ROOT, SKILL_NAME, SKILL_ROOT, SkillResolutionError,
                        resolve_ref, resolve_skill_dir, skill_slug)

MANIFEST = Path(__file__).resolve().parent / "dependencies.json"

_NUMERIC_DIR = re.compile(r"^(\d+)-(.+)$")
_FRONTMATTER_NAME = re.compile(r"^name:[ \t]*(.+?)[ \t]*$")


class DependencyError(Exception):
    """The dependency manifest itself cannot be read."""


def frontmatter_name(skill_md: Path) -> Optional[str]:
    """The `name:` scalar of a SKILL.md YAML frontmatter block, or None.

    An absent block, an unterminated block or a missing name is None: the same
    fail-closed answer as a name mismatch, never a guess from the file path.
    """
    try:
        lines = Path(skill_md).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        match = _FRONTMATTER_NAME.match(line)
        if match:
            return match.group(1).strip().strip("'\"")
    return None


def installer_registration_status(skill_md: Path) -> Dict[str, Any]:
    """Judge one skill registration file under either directory convention.

    999 links skills from CONTROL/bundled-skills.txt, so a bare slug
    (``black-friday-launcher``) and a numbered directory
    (``83-black-friday-launcher``) are equally valid. Both are accepted only
    when the directory name's slug and the SKILL.md frontmatter name agree; an
    ARCHIVED directory is always rejected.
    """
    skill_md = Path(skill_md)
    directory = skill_md.parent.name
    numeric = _NUMERIC_DIR.match(directory)
    slug = numeric.group(2) if numeric else directory
    name = frontmatter_name(skill_md)
    archived = "ARCHIVED" in directory
    ok = (skill_md.is_file() and not archived and name is not None
          and name == slug and (numeric is not None or directory == slug))
    return {
        "ok": ok,
        "directory": directory,
        "numeric_prefix": numeric is not None,
        "slug": slug,
        "frontmatter_name": name,
        "archived": archived,
    }


def _repo_root() -> Path:
    # Every manifest ref is repository-relative, and the repository root is the
    # discovered checkout root, never the skill's grandparent: in a deployed
    # tree the grandparent is .claude/skills, not the root.
    return REPO_ROOT


def load_manifest() -> Dict[str, Any]:
    if not MANIFEST.is_file():
        raise DependencyError(f"dependency manifest missing at {MANIFEST}")
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DependencyError(f"dependency manifest unreadable ({exc})") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        raise DependencyError("dependency manifest carries no entries array")
    return manifest


def _resolve(ref: str, root: Path, kind: str = "") -> tuple[Optional[Path], Optional[str]]:
    """Resolve a manifest ref by slug. A missing tree is a finding, not a crash.

    A skill_tree resolves by its slug under either naming convention even when the
    slug is not one of constants.SKILL_SLUGS (44 and 50 are not), so a 999 layout
    that renames the tree still resolves.
    """
    try:
        if kind == "skill_tree":
            return resolve_skill_dir(skill_slug(ref), root), None
        return resolve_ref(ref, root), None
    except SkillResolutionError as exc:
        return None, str(exc)


def _version(text: str) -> Optional[tuple]:
    """(major, minor, patch) from 'v2.1.28' or '0.2.5'; None when it holds no number."""
    numbers = re.findall(r"\d+", str(text).strip().lstrip("vV").split()[0] if str(text).strip() else "")
    return tuple(int(n) for n in (numbers + ["0", "0", "0"])[:3]) if numbers else None


def _version_floor(entry: Dict[str, Any], tree: Path) -> Optional[str]:
    """None when the tree meets entry['min_version']; otherwise the reason it does not.

    The tree's own skill-version.txt is the version source. An unreadable or
    unparseable version counts as unmet: a floor that cannot be read is never passed.
    """
    floor = entry.get("min_version")
    if not floor:
        return None
    try:
        found = (tree / "skill-version.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return f"{tree.name}/skill-version.txt unreadable; minimum version is {floor}"
    have, need = _version(found), _version(floor)
    if have is None or need is None or have < need:
        return f"version {found!r} is below the minimum {floor!r}"
    return None


def _requirement(ref: str) -> str:
    """The requirement line for a runtime package from requirements.txt ('jsonschema>=4.0'), else the bare name."""
    try:
        for line in (SKILL_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if re.match(re.escape(ref) + r"(?![\w.-])", line):
                return line
    except OSError:
        pass
    return ref


def _floor_unmet(ref: str) -> Optional[str]:
    """None when the installed package meets its '>=X.Y' floor, else why not.

    An old package imports fine, so an import alone does not prove the floor (the same
    rule as _oc_jsonschema_probe in lib-onboarding-state.sh). A version that cannot be
    read counts as unmet.
    """
    need = re.match(r"^[\w.-]+\s*>=\s*([\d.]+)", _requirement(ref))
    if need is None:
        return None
    try:
        have = metadata.version(ref)
    except Exception as exc:
        return f"its version could not be read ({type(exc).__name__})"
    if _version(have) is None or _version(have) < _version(need.group(1)):
        return f"installed {have} is older than the required {need.group(1)}"
    return None


def _present(entry: Dict[str, Any], root: Path) -> Dict[str, Any]:
    kind = entry["kind"]
    ref = entry["ref"]
    if kind in ("skill_tree", "shared_utils", "department_map_entry",
                "installer_registration"):
        target, error = _resolve(ref, root, kind)
        if target is None:
            return {"status": "missing", "evidence": error}
        if kind == "skill_tree" and target.exists():
            unmet = _version_floor(entry, target)
            if unmet:
                return {"status": "missing", "evidence": f"{ref} resolved={target}: {unmet}"}
        if kind == "installer_registration":
            judged = installer_registration_status(target)
            return {"status": "present" if judged["ok"] else "missing",
                    "evidence": f"{ref} resolved={target} "
                                f"exists={target.is_file()} "
                                f"directory={judged['directory']} "
                                f"numeric_prefix={judged['numeric_prefix']} "
                                f"frontmatter_name={judged['frontmatter_name']!r} "
                                f"slug={judged['slug']!r} "
                                f"archived={judged['archived']}"}
        return {"status": "present" if target.exists() else "missing",
                "evidence": f"{ref} resolved={target}"}
    if kind == "registry_line":
        target, error = _resolve(ref, root)
        if target is None:
            return {"status": "missing", "evidence": error}
        if not target.is_file():
            return {"status": "missing", "evidence": f"{ref} is absent"}
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"status": "unverifiable",
                    "evidence": f"{ref} unreadable ({exc})"}
        found = entry["match"] in json.dumps(data)
        return {"status": "present" if found else "missing",
                "evidence": f"'{entry['match']}' in {ref}: {found}"}
    if kind == "skill_number":
        from .constants import SKILL_NAME, SKILL_NUMBER

        try:
            # The registration record of the tree being checked, found by slug.
            registry = resolve_skill_dir(SKILL_NAME, root) / "registration.json"
        except SkillResolutionError:
            registry = None
        final = False
        if registry is not None and registry.is_file():
            try:
                final = bool(json.loads(registry.read_text(encoding="utf-8"))
                             ["skill"]["number_final"])
            except (OSError, ValueError, KeyError):
                final = False
        return {"status": "present" if final else "missing",
                "evidence": f"SKILL_NUMBER={SKILL_NUMBER!r} number_final={final} "
                            f"registry={registry}"}
    if kind == "runtime_package":
        # A real import, not find_spec: find_spec only proves the package's files
        # are on the path, so jsonschema with its own dependency (attrs) missing
        # read as present and then failed inside the Skill 79 validator.
        try:
            importlib.import_module(ref)
            unmet = _floor_unmet(ref)
            found, failure = unmet is None, (f"; {unmet}" if unmet else "")
        except Exception as exc:  # a dependency of the package failing counts
            found, failure = False, f"; import failed: {type(exc).__name__}: {exc}"
        isolated = bool(getattr(sys.flags, "isolated", 0))
        return {"status": "present" if found else "missing",
                "evidence": f"import {ref!r} under {sys.executable} -> {found}{failure}; "
                            f"isolated_interpreter={isolated}"}
    return {"status": "unverifiable", "evidence": f"unknown kind {kind!r}"}


def _registered_enabled(base: Path) -> bool:
    """True when the skill's registration.json records enabled_in_999: true."""
    try:
        path = resolve_skill_dir(SKILL_NAME, base) / "registration.json"
        record = json.loads(path.read_text(encoding="utf-8"))
    except (SkillResolutionError, OSError, ValueError):
        return False
    return (record.get("enablement") or {}).get("enabled_in_999") is True


def check(root: Optional[Path] = None) -> Dict[str, Any]:
    """Report what is present and what is missing before a 999 enablement."""
    manifest = load_manifest()
    base = Path(root) if root else _repo_root()
    entries: List[Dict[str, Any]] = []
    for entry in manifest["entries"]:
        result = _present(entry, base)
        entries.append({
            "id": entry["id"],
            "kind": entry["kind"],
            "ref": entry["ref"],
            "required": bool(entry.get("required")),
            "why": entry.get("why", ""),
            "status": result["status"],
            "evidence": result["evidence"],
        })
    present = [e["id"] for e in entries if e["status"] == "present"]
    missing = [e["id"] for e in entries if e["status"] == "missing"]
    unverifiable = [e["id"] for e in entries if e["status"] == "unverifiable"]
    blockers = [e["id"] for e in entries
                if e["status"] != "present" and e["required"]]
    return {
        "target": manifest.get("target"),
        "enabled_in_999": _registered_enabled(base) and not blockers,
        "would_enable": not blockers,
        "seen_from": str(base),
        "entries": entries,
        "present": present,
        "missing": missing,
        "unverifiable": unverifiable,
        "blockers": blockers,
    }


def _pip_install(spec: str) -> bool:
    """pip-install spec into the shared pydeps folder, under THIS interpreter (sys.executable).

    `--target` is the one install an externally-managed Python (Homebrew, Debian; PEP 668) accepts without
    a flag, and the folder is versioned per interpreter and, on a Docker box, lives under /data/.openclaw,
    so it survives a container recreate. There is no `--user` and no `--break-system-packages` tier: they are
    refused or forbidden on exactly the boxes this exists for. If pip itself is missing it returns False.
    """
    target = pydeps.install_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        run = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                              "--no-input", "--upgrade", "--target", str(target), spec],
                             capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return False
    return run.returncode == 0


def ensure_runtime_packages(root: Optional[Path] = None,
                            install: Callable[[str], bool] = _pip_install) -> Dict[str, Any]:
    """Install any missing required runtime package itself, then return the re-checked report.

    The client is never asked to install software: a package that is not importable (or is
    below its floor) is installed here into the shared pydeps folder, put on sys.path, and verified by the
    same real import `check` uses. This is also what survives a container recreate or a Python upgrade
    (a new versioned folder): the next launch repairs itself before anything is built. A package that
    still fails stays a blocker for `require`, which tells the operator, not the client.
    """
    report = check(root)
    todo = [e for e in report["entries"]
            if e["kind"] == "runtime_package" and e["required"] and e["status"] != "present"]
    if not todo:
        return report
    for entry in todo:
        install(_requirement(entry["ref"]))
    importlib.invalidate_caches()
    pydeps.activate()  # the folder may have just been created
    report = check(root)
    # The operator note is judged on the re-check (the same real import), never on install()'s return alone:
    # a pip that ran but left the package unimportable, or no pip at all, must not read as success.
    still = [e["ref"] for e in report["entries"]
             if e["kind"] == "runtime_package" and e["required"] and e["status"] != "present"]
    if still:
        print("[launcher] setup: a missing runtime package could NOT be installed automatically (%s); "
              "operator note, not for the client: python3 -m launcher_core.cli dependencies --install "
              "(never --break-system-packages, never a venv)" % ", ".join(still), file=sys.stderr)
    else:
        print("[launcher] setup: a missing runtime package was installed automatically "
              "(operator note, not for the client)", file=sys.stderr)
    return report


def require(root: Optional[Path] = None) -> Dict[str, Any]:
    """The preflight a build runs first: return the report, or refuse naming every blocker.

    A green preflight must mean the launch can run, so dispatch and assemble call this
    before they touch a page. A missing runtime package is installed first
    (ensure_runtime_packages); any other required entry that is missing, below its minimum
    version, or unverifiable blocks. Nothing has been built or spent when it raises.
    """
    report = ensure_runtime_packages(root)
    if report["blockers"]:
        detail = {e["id"]: e for e in report["entries"]}
        message = ("AF-LAUNCH-DEPENDENCY: required dependency not satisfied: "
                   + "; ".join(f"{i} [{detail[i]['ref']}] {detail[i]['status']} ({detail[i]['evidence']})"
                               for i in report["blockers"])
                   + ". Nothing was built and nothing was spent.")
        if any(detail[i]["kind"] == "runtime_package" for i in report["blockers"]):
            message += (f" The launcher already tried to install the package itself and could not. "
                        f"This is for the operator, not the client; the client is only told that setup "
                        f"needs a few more minutes. Operator fix (never --break-system-packages, never a "
                        f"venv): python3 -m launcher_core.cli dependencies --install, which installs into "
                        f"{pydeps.install_dir()}. If pip is missing for {sys.executable}, install it first "
                        f"(Debian: apt-get install python3-pip).")
        raise DependencyError(message)
    return report
