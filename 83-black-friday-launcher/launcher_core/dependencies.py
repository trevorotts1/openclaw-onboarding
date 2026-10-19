"""Dependency package for enabling the Launcher in 999.

Reads the manifest and reports, per entry, whether it is PRESENT in this
repository, MISSING, or UNVERIFIABLE, with the evidence used. It writes nothing
outside this skill and never claims 999 is enabled: the package is a preflight,
and the manifest's `enabled_in_999` stays false.

A missing entry is a finding, not a crash; `check()` exits 0 whenever the
manifest itself is readable, so the report can be run at any time.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import (REPO_ROOT, SkillResolutionError, resolve_ref,
                        resolve_skill_dir)

MANIFEST = Path(__file__).resolve().parent / "dependencies.json"


class DependencyError(Exception):
    """The dependency manifest itself cannot be read."""


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
    if manifest.get("enabled_in_999") is not False:
        raise DependencyError(
            "the manifest must record enabled_in_999: false; this package does "
            "not enable anything")
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
            name = target.parent.name
            numeric = name.split("-", 1)[0].isdigit()
            ok = target.is_file() and numeric and "ARCHIVED" not in name
            return {"status": "present" if ok else "missing",
                    "evidence": f"{ref} resolved={target} exists={target.is_file()} "
                                f"numeric_prefix={numeric} archived={'ARCHIVED' in name}"}
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
        "enabled_in_999": False,
        "would_enable": not blockers,
        "seen_from": str(base),
        "entries": entries,
        "present": present,
        "missing": missing,
        "unverifiable": unverifiable,
        "blockers": blockers,
    }
