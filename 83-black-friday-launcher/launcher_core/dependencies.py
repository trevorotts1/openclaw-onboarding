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

import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import (REPO_ROOT, SKILL_NAME, SkillResolutionError,
                        resolve_ref, resolve_skill_dir)

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


def _resolve(ref: str, root: Path) -> tuple[Optional[Path], Optional[str]]:
    """Resolve a manifest ref by slug. A missing tree is a finding, not a crash."""
    try:
        return resolve_ref(ref, root), None
    except SkillResolutionError as exc:
        return None, str(exc)


def _present(entry: Dict[str, Any], root: Path) -> Dict[str, Any]:
    kind = entry["kind"]
    ref = entry["ref"]
    if kind in ("skill_tree", "shared_utils", "department_map_entry",
                "installer_registration"):
        target, error = _resolve(ref, root)
        if target is None:
            return {"status": "missing", "evidence": error}
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
        try:
            found = importlib.util.find_spec(ref) is not None
        except (ImportError, ValueError):
            found = False
        isolated = bool(getattr(__import__("sys").flags, "isolated", 0))
        return {"status": "present" if found else "missing",
                "evidence": f"importlib.util.find_spec({ref!r}) -> {found}; "
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
