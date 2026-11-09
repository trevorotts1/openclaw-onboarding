"""Dependency package for enabling the Launcher in 999.

Reads the manifest and reports, per entry, whether it is PRESENT in this
repository, MISSING, or UNVERIFIABLE, with the evidence used. It writes nothing
outside this skill. `enabled_in_999` in the report is true only when the skill's
own registration.json records the enablement AND no required entry is
missing, so the flag is evidence-derived, never hard-coded.

A missing entry is a finding, not a crash; `check()` exits 0 whenever the
manifest itself is readable, so the report can be run at any time.

`dependencies.json` is the ONLY executable source of truth for what the Launcher
requires: `registration.json` and `skill.json` carry a pointer to it (plus a
digest of the requirement set), never their own list. `metadata_spine()` checks
that pointer and reports a metadata/manifest disagreement as a finding in the
report, never as a crash and never as a blocker: those two files record nothing
that runs.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import pydeps
from .constants import (REPO_ROOT, SKILL_NAME, SKILL_ROOT, SkillResolutionError,
                        resolve_ref, resolve_skill_dir, skill_slug)
from .image_plan import DEFAULT_PROVIDER

MANIFEST = Path(__file__).resolve().parent / "dependencies.json"
MANIFEST_REF = "launcher_core/dependencies.json"
# The two human-readable metadata records. They point at MANIFEST and are never
# a second list of requirements; metadata_spine() is what proves they cannot drift.
METADATA_SPINES = ("registration.json", "skill.json")
_SPINE_KINDS = ("skill_tree", "shared_utils")

# The launch modes a preflight can be asked about. Each maps to the steps in
# cli.py that really run: `plan`/`route` compile the graph, `questions` reads the
# shared interview, `dispatch` builds pages (stub or paid), `assemble` packages
# them. A mode is not a label: it decides which SELECTED-CONDITIONAL entries are
# part of the closure and therefore which of them can block.
LAUNCH_MODES = ("plan", "questions", "dispatch", "dispatch-kie", "assemble")
DEFAULT_MODE = "plan"

CLASS_REQUIRED = "required"
CLASS_SELECTED = "selected_conditional"
CLASS_OPTIONAL = "unselected_optional"
_CLASSES = (CLASS_REQUIRED, CLASS_SELECTED, CLASS_OPTIONAL)

# File-shaped entries: a path that must exist, never a tree digest or a version.
_FILE_KINDS = ("shared_utils", "department_map_entry", "installer_registration",
               "schema", "template", "sop")

# A `sop` entry resolves the SOP file AND a read receipt under the skill's own
# tree. The receipt names the SOP's repo path and its sha256, so a read of an
# older copy stops counting the moment the SOP changes.
SOP_RECEIPT_DIR = "receipts/sop-read"


def entry_class(entry: Dict[str, Any]) -> str:
    """The entry's closure class. The v1 `required` boolean is the fallback, so an
    older manifest cannot silently read as all-required."""
    declared = entry.get("class")
    if declared in _CLASSES:
        return declared
    return CLASS_REQUIRED if entry.get("required") else CLASS_OPTIONAL


def entry_modes(entry: Dict[str, Any]) -> Tuple[str, ...]:
    """The modes this entry is part of. No `modes` key means every mode, which is
    the only honest default for code the launcher always loads."""
    declared = entry.get("modes")
    if isinstance(declared, list) and declared:
        return tuple(str(m) for m in declared)
    return LAUNCH_MODES


def selected(entry: Dict[str, Any], mode: str) -> bool:
    """True when this entry belongs to `mode`'s closure."""
    return mode in entry_modes(entry)


def blocking(entry: Dict[str, Any], mode: str, status: str) -> bool:
    """True when a non-present entry must refuse this mode.

    A REQUIRED entry blocks every mode it belongs to. A SELECTED-CONDITIONAL entry
    blocks only the modes it names — and only while it is selected, which is why
    the same manifest can report the KIE helpers for a paid run and stay green for
    a stub one. An UNSELECTED-OPTIONAL entry never blocks.
    """
    if status == "present" or not selected(entry, mode):
        return False
    cls = entry_class(entry)
    if cls == CLASS_REQUIRED:
        return True
    return cls == CLASS_SELECTED  # `selected` above already proved the mode names it


def detect_harness(root: Optional[Path] = None) -> str:
    """Which supported layout this skill is running from, from the filesystem.

    The closure is the same graph in every harness; what changes is where a skill
    tree resolves, and that is constants.resolve_skill_dir's job. This names the
    layout so a report says which one was measured, never a guess.
    """
    base = Path(root) if root is not None else REPO_ROOT
    try:
        inside = SKILL_ROOT.resolve().relative_to(base.resolve()).parts
    except ValueError:
        inside = ()
    if inside[:2] == (".claude", "skills") or inside[:1] == ("skills",):
        return "claude-nine"
    if len(inside) == 1:
        # The skill is a direct child of the checkout: the onboarding repository.
        return "openclaw"
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return "claude-code"
    return "openclaw"


def mode_for_intake(payload: Any) -> str:
    """The dispatch mode an intake selects: paid KIE images, or the stub practice run.

    A paid run's pictures are drawn by the KIE transport, so its closure carries the
    provider helpers; a practice run draws placeholders and does not. This reads the
    CLAIM (test_only and the provider), never a plan hash, so it can run before the
    approval is verified — it only decides which dependencies are checked.
    """
    doc = payload if isinstance(payload, dict) else {}
    paid = doc.get("test_only") is False
    provider = (doc.get("image_plan") or {}).get("image_provider") \
        if isinstance(doc.get("image_plan"), dict) else None
    provider = provider or DEFAULT_PROVIDER
    return "dispatch-kie" if paid and provider == "kie" else "dispatch"

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


def requirement_set(manifest: Dict[str, Any]) -> List[str]:
    """One canonical line per entry: what a metadata spine's stamp is computed over."""
    return sorted(
        f"{e.get('id')}|{e.get('kind')}|{e.get('ref')}|{e.get('min_version', '')}|"
        f"{int(bool(e.get('required')))}"
        for e in manifest["entries"])


def requirements_digest(manifest: Dict[str, Any]) -> str:
    """sha256 over requirement_set: editing a `why` or the note does not move it.

    A change to any id, kind, ref, minimum version or required flag does, which is
    exactly the change a pointer stamp must catch.
    """
    return hashlib.sha256("\n".join(requirement_set(manifest)).encode("utf-8")).hexdigest()


def _declared_refs(manifest: Dict[str, Any]) -> set:
    """The required skill trees and shared modules, by the name a spine would spell."""
    return {skill_slug(e["ref"]) if e["kind"] == "skill_tree" else e["ref"]
            for e in manifest["entries"]
            if e.get("kind") in _SPINE_KINDS and e.get("required")}


def _legacy_named(spine: Any) -> set:
    """The names in a free-text depends_on, normalised the way the manifest spells them."""
    names = spine.keys() if isinstance(spine, dict) else (spine or ())
    out = set()
    for name in names:
        text = str(name)
        out.add(text if text.startswith("shared-utils/") else skill_slug(text.split("/", 1)[0]))
    return out


def _pointer_findings(name: str, spine: Dict[str, Any], manifest: Dict[str, Any]) -> List[str]:
    """A pointer is checked for a stale target, digest, or count. Wording is never checked."""
    findings: List[str] = []
    target = str(spine.get("authoritative_manifest") or "").lstrip("./")
    if not target.endswith(MANIFEST_REF):
        findings.append(f"{name}: depends_on points at {target!r}, not {MANIFEST_REF!r}; "
                        "the manifest is the only executable source of truth")
    want = requirements_digest(manifest)
    have = str(spine.get("requirements_digest") or "")
    if have != want:
        findings.append(f"{name}: requirements_digest is {have or 'absent'}, but {MANIFEST_REF} "
                        f"now hashes to {want}; re-stamp the pointer")
    for key, actual in (("manifest_entry_count", len(manifest["entries"])),
                        ("required_entry_count",
                         sum(1 for e in manifest["entries"] if e.get("required")))):
        if key in spine and spine[key] != actual:
            findings.append(f"{name}: {key} is {spine[key]!r}, but the manifest has {actual}")
    return findings


def metadata_spine(manifest: Dict[str, Any], base: Optional[Path] = None) -> Dict[str, Any]:
    """Check registration.json and skill.json against the executable manifest.

    A pointer is checked for a stale target, digest or count. A legacy free-text
    list is compared name by name and reported as extra or omitted. A list that
    still happens to agree is still reported, because a second list is the drift
    this check exists to prevent. Nothing here raises and nothing blocks a build.
    """
    findings: List[str] = []
    skill_dir: Optional[Path] = SKILL_ROOT
    if base is not None:
        try:
            skill_dir = resolve_skill_dir(SKILL_NAME, base)
        except SkillResolutionError as exc:
            # Never fall back to this checkout's own tree: a caller asking about another
            # root would then be reading the wrong files and still see no findings.
            findings.append(f"{SKILL_NAME}: {exc}; neither metadata spine could be checked "
                            f"against {MANIFEST_REF}")
            skill_dir = None
    for name in (METADATA_SPINES if skill_dir is not None else ()):
        path = skill_dir / name
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            findings.append(f"{name}: unreadable ({type(exc).__name__}: {exc}); it cannot be "
                            f"confirmed against {MANIFEST_REF}")
            continue
        spine = record.get("depends_on") if isinstance(record, dict) else None
        if isinstance(spine, dict) and "authoritative_manifest" in spine:
            findings.extend(_pointer_findings(name, spine, manifest))
        elif isinstance(spine, (dict, list)):
            named, declared = _legacy_named(spine), _declared_refs(manifest)
            extra, absent = sorted(named - declared), sorted(declared - named)
            if extra:
                findings.append(f"{name}: depends_on names {extra}, which {MANIFEST_REF} does not "
                                "require; the list contradicts the manifest")
            if absent:
                findings.append(f"{name}: depends_on omits {absent}, which {MANIFEST_REF} requires")
            if not extra and not absent:
                findings.append(f"{name}: depends_on still repeats the requirement list; replace it "
                                f"with the pointer to {MANIFEST_REF} so it cannot drift")
        else:
            findings.append(f"{name}: has no depends_on pointer to {MANIFEST_REF}")
    return {
        "authoritative_manifest": MANIFEST_REF,
        "manifest_schema": manifest.get("schema"),
        "requirements_digest": requirements_digest(manifest),
        "entry_count": len(manifest["entries"]),
        "required_entry_count": sum(1 for e in manifest["entries"] if e.get("required")),
        "findings": findings,
    }


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
    if kind == "sop":
        target, error = _resolve(ref, root, kind)
        if target is None or not target.is_file():
            return {"status": "missing", "evidence": error or f"{ref} is absent"}
        judged = _sop_receipt(entry, root, target)
        if not judged["ok"]:
            return {"status": "missing",
                    "evidence": f"{ref} resolved={target}: {judged['why']}"}
        return {"status": "present",
                "evidence": f"{ref} resolved={target} receipt={judged['receipt']}"}
    if kind in ("skill_tree",) + _FILE_KINDS:
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


def _sha256_file(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None

def _sop_receipt(entry: Dict[str, Any], root: Path, target: Path) -> Dict[str, Any]:
    """The read receipt a `sop` entry requires, or why it does not count."""
    declared = str(entry.get("receipt") or "").strip()
    rel = declared or f"{SOP_RECEIPT_DIR}/{target.stem}.json"
    try:
        receipt = resolve_skill_dir(SKILL_NAME, root) / rel
    except SkillResolutionError as exc:
        return {"ok": False, "why": f"receipt path unresolved ({exc})"}
    if not receipt.is_file():
        return {"ok": False, "why": f"no read receipt at {rel}"}
    try:
        record = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "why": f"read receipt {rel} unreadable"}
    if not isinstance(record, dict):
        return {"ok": False, "why": f"read receipt {rel} is not a record"}
    want = _sha256_file(target)
    if want is None:
        return {"ok": False, "why": f"{entry['ref']} unreadable"}
    have = str(record.get("sha256") or "")
    if have != want:
        return {"ok": False,
                "why": f"read receipt {rel} is stale (sha256 {have or 'absent'} != {want})"}
    named = str(record.get("sop") or "")
    if named and Path(named).name != target.name:
        return {"ok": False,
                "why": f"read receipt {rel} names {named!r}, not {entry['ref']!r}"}
    return {"ok": True, "why": "", "receipt": str(receipt)}

def _registered_enabled(base: Path) -> bool:
    """True when the skill's registration.json records enabled_in_999: true."""
    try:
        path = resolve_skill_dir(SKILL_NAME, base) / "registration.json"
        record = json.loads(path.read_text(encoding="utf-8"))
    except (SkillResolutionError, OSError, ValueError):
        return False
    return (record.get("enablement") or {}).get("enabled_in_999") is True


def check(root: Optional[Path] = None, mode: Optional[str] = None) -> Dict[str, Any]:
    """Report what is present and what is missing before a 999 enablement.

    With `mode`, every entry is also classified for that launch mode: REQUIRED
    (blocks), SELECTED-CONDITIONAL (blocks only when this mode selects it) or
    UNSELECTED-OPTIONAL (reported, never blocks). Without `mode` the report is the
    v1 all-modes view, so an existing caller keeps its meaning.
    """
    manifest = load_manifest()
    base = Path(root) if root else _repo_root()
    active = mode or DEFAULT_MODE
    if active not in LAUNCH_MODES:
        raise DependencyError(f"unknown launch mode {active!r}; supported: {list(LAUNCH_MODES)}")
    entries: List[Dict[str, Any]] = []
    for entry in manifest["entries"]:
        result = _present(entry, base)
        cls = entry_class(entry)
        entries.append({
            "id": entry["id"],
            "kind": entry["kind"],
            "ref": entry["ref"],
            "required": bool(entry.get("required")),
            "class": cls,
            "modes": list(entry_modes(entry)),
            "selected": selected(entry, active),
            "blocking": blocking(entry, active, result["status"]),
            "why": entry.get("why", ""),
            "status": result["status"],
            "evidence": result["evidence"],
        })
    present = [e["id"] for e in entries if e["status"] == "present"]
    missing = [e["id"] for e in entries if e["status"] == "missing"]
    unverifiable = [e["id"] for e in entries if e["status"] == "unverifiable"]
    blockers = [e["id"] for e in entries if e["blocking"]]
    closure = closure_from(entries, manifest, active, base)
    return {
        "target": manifest.get("target"),
        "mode": active,
        "harness": detect_harness(base),
        "enabled_in_999": _registered_enabled(base) and not blockers,
        "would_enable": not blockers,
        "seen_from": str(base),
        # The metadata spines carry no requirements of their own; a mismatch here is a
        # finding in this report, never a blocker and never an exception.
        "metadata": metadata_spine(manifest, base),
        "entries": entries,
        "present": present,
        "missing": missing,
        "unverifiable": unverifiable,
        "blockers": blockers,
        "closure": closure,
    }


def closure_from(entries: List[Dict[str, Any]], manifest: Dict[str, Any],
                 mode: str, base: Path) -> Dict[str, Any]:
    """The mode's installed closure: what this mode really loads, by class.

    This is the answer to "the 19 checks are not 19 skills". Each row is one
    resolution the mode performs — code, schema, role/prompt template, brand rule,
    shared package or provider helper — with the status of that resolution. The
    three lists are never mixed: a selected entry that is missing is a refusal,
    an unselected optional one is information.
    """
    required = [e["id"] for e in entries if e["selected"] and e["class"] == CLASS_REQUIRED]
    selected_cond = [e["id"] for e in entries
                     if e["selected"] and e["class"] == CLASS_SELECTED]
    optional = [e["id"] for e in entries if e["class"] == CLASS_OPTIONAL]
    unselected = [e["id"] for e in entries
                  if not e["selected"] and e["class"] != CLASS_OPTIONAL]
    return {
        "mode": mode,
        "harness": detect_harness(base),
        "declared_modes": sorted((manifest.get("closure") or {}).get("modes") or {}),
        "rows": [{"id": e["id"], "kind": e["kind"], "ref": e["ref"],
                  "class": e["class"], "status": e["status"]} for e in entries],
        "required": required,
        "selected_conditional": selected_cond,
        "unselected_optional": optional,
        "not_in_this_mode": unselected,
        "required_missing": [e["id"] for e in entries
                             if e["selected"] and e["class"] == CLASS_REQUIRED
                             and e["status"] != "present"],
        "selected_missing": [e["id"] for e in entries
                             if e["selected"] and e["class"] == CLASS_SELECTED
                             and e["status"] != "present"],
        "counts": {"entries": len(entries), "required": len(required),
                   "selected_conditional": len(selected_cond),
                   "unselected_optional": len(optional)},
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
                            install: Callable[[str], bool] = _pip_install,
                            mode: Optional[str] = None) -> Dict[str, Any]:
    """Install any missing required runtime package itself, then return the re-checked report.

    The client is never asked to install software: a package that is not importable (or is
    below its floor) is installed here into the shared pydeps folder, put on sys.path, and verified by the
    same real import `check` uses. This is also what survives a container recreate or a Python upgrade
    (a new versioned folder): the next launch repairs itself before anything is built. A package that
    still fails stays a blocker for `require`, which tells the operator, not the client.
    """
    report = check(root, mode)
    todo = [e for e in report["entries"]
            if e["kind"] == "runtime_package" and e["required"] and e["status"] != "present"]
    if not todo:
        return report
    for entry in todo:
        install(_requirement(entry["ref"]))
    importlib.invalidate_caches()
    pydeps.activate()  # the folder may have just been created
    report = check(root, mode)
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


def require(root: Optional[Path] = None, mode: Optional[str] = None) -> Dict[str, Any]:
    """The preflight a build runs first: return the report, or refuse naming every blocker.

    A green preflight must mean the launch can run, so dispatch and assemble call this
    before they touch a page. A missing runtime package is installed first
    (ensure_runtime_packages); any other entry that blocks THIS launch mode — required
    for every mode, or selected by a mode that names it — blocks when it is missing,
    below its minimum version, or unverifiable. Nothing has been built or spent when it
    raises.
    """
    report = ensure_runtime_packages(root)
    if mode and mode != report.get("mode"):
        report = check(root, mode)
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
