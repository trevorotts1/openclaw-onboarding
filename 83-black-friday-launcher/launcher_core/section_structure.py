"""F17 item 5: each page role's OWN section structure, and the check that a page's designs match it.

A launch does not have one design skeleton. Skill 71 already routes by page role
(``scripts/stage_executor.py check_section_count``), and this module resolves the SAME structure for
a package piece by loading Skill 71's own resolvers instead of re-typing a sequence:

1. ``references/page-structures.json`` ``roles.<role>`` — the downsell page's eight bands;
2. ``references/copy-specs/roles/<role>.json`` through ``scripts/role_spec.py`` — the checkout's five;
3. the registered copy form for the role through ``scripts/copy_forms.py`` — the thank-you and
   product-selection pages (five) and the upsell page (eight);
4. the two landing pages through ``references/page-kinds.json`` and ``scripts/page_role.py`` — the
   signature sales page (Standard 12, Long-Form 15) and the signature opt-in page (Long-Form 15).

A piece is checked against the sequence of ITS OWN role, so the main sales-page skeleton is never
forced onto a checkout, an upsell or a thank-you page, and a section number a role does not have is
named rather than counted. Only a role whose structure genuinely cannot be resolved is refused, and
the refusal names the role and the reason — the sales-page skeleton is never applied in its place.

Section identity is the number in the file's own label (``..._s03-of-08_offer.png``), read by the
caller's ``section_identity``; a count is not a structure.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .constants import REPO_ROOT, resolve_ref

CODE = "AF-LAUNCH-SECTION-STRUCTURE"
SKILL71 = "71-blackceo-signature-page"
STRUCTURES_REF = f"{SKILL71}/references/page-structures.json"
PAGE_KINDS_REF = f"{SKILL71}/references/page-kinds.json"
ROLE_SPECS_DIR = f"{SKILL71}/references/copy-specs/roles"
COPY_SPECS_DIR = f"{SKILL71}/references/copy-specs"
DEFAULT_KIND = "opt_in"  # a landing piece with no page kind is the opt-in landing page
_MODULES: Dict[str, Any] = {}


def _read(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _module(filename: str, root: Optional[Path] = None):
    """One Skill 71 script by path, loaded once per root: its own resolver, never a retyped copy."""
    base = Path(root) if root is not None else REPO_ROOT
    key = f"{base.resolve()}|{filename}"
    if key in _MODULES:
        return _MODULES[key]
    path = resolve_ref(f"{SKILL71}/scripts/{filename}", base)
    if not path.is_file():
        raise LookupError(f"{SKILL71}/scripts/{filename} is not installed")
    spec = importlib.util.spec_from_file_location(f"launcher_section_{Path(filename).stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    _MODULES[key] = module
    return module


def _sequences_of(spec: dict, root: Optional[Path]) -> List[List[str]]:
    """Every sequence Skill 71 accepts for this spec: its own plus the optional-children expansions.

    ``page_role.allowed_sequences`` is the one resolver the request builder and the executor read,
    so a child-section expansion (5 -> 5A, 5B, 5C) is accepted here exactly when 71 accepts it.
    """
    try:
        return [list(seq) for seq in _module("page_role.py", root).allowed_sequences(spec, None)]
    except (LookupError, AttributeError, KeyError, TypeError, ValueError):
        return [list(spec["sequence"])]


def _known(out: Dict[str, Any], sequences: List[List[str]], source: str,
           sections: Dict[str, Any]) -> Dict[str, Any]:
    keep = [seq for seq in sequences if seq]
    if not keep:
        out["reason"] = f"{source} declares no section sequence"
        return out
    out.update(state="known", source=source, sequences=keep, sections=sections, reason=None)
    return out


def _structures_entry(role: str, instance: Optional[str], root: Optional[Path]):
    """The page-structures.json entry for the role (or its role instance), or None."""
    doc = _read(resolve_ref(STRUCTURES_REF, root or REPO_ROOT))
    if not isinstance(doc, dict):
        return None, None
    for candidate in (role, instance):
        entry = ((doc.get("roles") or {}).get(candidate)) if candidate else None
        if isinstance(entry, dict) and entry.get("sequence"):
            return entry, f"{STRUCTURES_REF} roles.{candidate}"
    return None, None


def _landing_versions(kind: Optional[str], root: Optional[Path]) -> List[str]:
    """The copy versions a landing piece may use, from Skill 71's own page-kinds table."""
    doc = _read(resolve_ref(PAGE_KINDS_REF, root or REPO_ROOT))
    kinds = (doc or {}).get("kinds") if isinstance(doc, dict) else None
    entry = (kinds or {}).get(kind or DEFAULT_KIND) or {}
    versions = [str(v) for v in (entry.get("copy_versions") or []) if v]
    return versions or [str((kinds or {}).get(DEFAULT_KIND, {}).get("default_copy_version") or "long-form")]


def resolve(piece: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    """This piece's role section structure.

    Returns ``{"role", "state": "known"|"unknown", "source", "sequences", "sections", "reason"}``:
    ``sequences`` are every accepted ordered id list for the role and ``sections`` maps an id to the
    role's own entry (name, page_role or layout_tag) where the source declares one. ``unknown`` names
    the reason; it never silently falls back to another role's skeleton.
    """
    role = str(piece.get("role") or "")
    instance = str(piece.get("role_instance") or "") or None
    kind = str(piece.get("page_kind") or "") or None
    out: Dict[str, Any] = {"role": role, "state": "unknown", "source": None, "sequences": [],
                           "sections": {}, "reason": None}
    if not role:
        out["reason"] = "the piece names no page role"
        return out
    entry, source = _structures_entry(role, instance, root)
    if entry is not None:
        sections = {str(s["id"]): s for s in entry.get("sections") or [] if isinstance(s, dict) and "id" in s}
        return _known(out, [entry["sequence"]], str(source), sections)
    try:
        spec = _module("role_spec.py", root).load(role)
    except (LookupError, ValueError):
        spec = None
    if isinstance(spec, dict) and spec.get("sequence"):
        sections = {str(s["id"]): s for s in spec.get("sections") or [] if isinstance(s, dict) and "id" in s}
        return _known(out, _sequences_of(spec, root), f"{ROLE_SPECS_DIR}/{role}.json", sections)
    try:
        forms = _module("copy_forms.py", root)
        form = forms.form_for_role(role)
        form_spec = forms.load_spec(form) if form else None
        spec_file = forms.SPEC_FILES.get(form) if form else None
    except (LookupError, KeyError, ValueError):
        form_spec, spec_file = None, None
    if isinstance(form_spec, dict) and form_spec.get("sequence"):
        sections = {str(s["id"]): s for s in form_spec.get("sections") or []
                    if isinstance(s, dict) and "id" in s}
        return _known(out, _sequences_of(form_spec, root), f"{COPY_SPECS_DIR}/{spec_file}", sections)
    if role == "landing":
        page_role = None
        try:
            page_role = _module("page_role.py", root)
        except LookupError as exc:
            out["reason"] = str(exc)
            return out
        sequences, sources, sections = [], [], {}
        for version in _landing_versions(kind, root):
            spec = page_role.load_spec(version)
            if not isinstance(spec, dict) or not spec.get("sequence"):
                continue
            sequences.extend(page_role.allowed_sequences(spec, None))
            sources.append(f"{COPY_SPECS_DIR}/{version}-v6.json")
            for row in spec.get("sections") or []:
                if isinstance(row, dict) and "id" in row:
                    sections.setdefault(str(row["id"]), row)
        return _known(out, sequences, " + ".join(sources), sections)
    out["reason"] = (f"no page-structures.json role entry, no {ROLE_SPECS_DIR}/{role}.json and no "
                     f"registered copy form names the page role {role!r}")
    return out


def number_sets(structure: Dict[str, Any]) -> List[Set[int]]:
    """The label numbers each accepted sequence of the role carries.

    Skill 71 labels a section by its POSITION in the page (``_s03-of-15_``) and a long-form landing
    sequence uses lettered sub-ids for its extra entries (1, 2, 2A, 3, 3A ... 12) — fifteen positions
    numbered one to fifteen. So the numbers a page must carry are exactly 1..len(sequence): the
    structure decides the count, and a count is not a structure.
    """
    out: List[Set[int]] = []
    for seq in structure.get("sequences") or []:
        numbers = set(range(1, len(seq) + 1))
        if seq and numbers not in out:
            out.append(numbers)
    return out


def section_problems(piece: Dict[str, Any], key: str, found: Dict[str, List[str]],
                     identity: Callable[[str], Optional[Dict[str, Any]]],
                     root: Optional[Path] = None) -> List[str]:
    """Every way this page's section images miss the section structure of its OWN role.

    ``found`` is {deliverable kind: [artifact paths]} and ``identity`` reads a path's own label. A
    page's section images must be numbered 1..N where N is the number of sections ITS role has (the
    downsell's 1..8, the checkout's 1..5, the opt-in landing's 1..15), each number once, and the
    wrong numbers are named — so the main sales page's twelve positions are never accepted for
    another role, and a page numbered 5..12 is not the page its role says it is.
    """
    structure = resolve(piece, root)
    role = str(piece.get("role") or "")
    if structure.get("state") != "known":
        return [f"{CODE}: {key} (role {role or '?'}) has no section structure that resolves "
                f"({structure.get('reason') or 'unknown'}); the main sales-page skeleton is not applied "
                "in its place, so this page's sections cannot be checked"]
    want = number_sets(structure)
    fails: List[str] = []
    for kind, paths in sorted(found.items()):
        if not kind.endswith("_section"):
            continue
        labels = [ident for ident in (identity(p) for p in paths) if ident]
        actual = {int(ident["section"]) for ident in labels}
        if not actual or actual in want:
            continue
        totals = sorted({int(ident["of"]) for ident in labels if ident.get("of")})
        nearest = min(want, key=lambda w: len(w.symmetric_difference(actual)))
        missing = sorted(nearest - actual)
        extra = sorted(actual - nearest)
        detail = []
        if missing:
            detail.append("no section " + ", ".join(str(n) for n in missing))
        if extra:
            detail.append("a section " + ", ".join(str(n) for n in extra) + " this role does not have")
        if totals and totals != [len(nearest)]:
            detail.append(f"its labels say the page has {totals[0]} section(s) and this role has "
                          f"{len(nearest)}")
        fails.append(f"{CODE}: {key} (role {role}) {kind.replace('_', ' ')} does not match this page's "
                     f"own section structure ({structure['source']}): " + "; ".join(detail))
    return fails
