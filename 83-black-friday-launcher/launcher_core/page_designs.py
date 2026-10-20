"""AF-LAUNCH-PAGE-DESIGNS: every page of a launch ships its full set of designs, clearly labeled.

A package that holds a page without its desktop AND mobile wireframes and mockups, the two combined
review PDFs per kind, the overview boards and the clear labels is not a delivered package, however
many hashes match. This module knows what "a full set" is and reads it from one place:

* ``49-signature-funnel/structure/page_types.json`` (contract C2) when it exists, so a page type
  added there is required here with no code change;
* otherwise the built-in set below, recorded as ``source: "builtin"`` so the report says so.

Deliverable kinds are inferred from the file names Skill 71's ``deliverable_labels.py`` produces, or
taken from an explicit ``kind`` on the artifact. A file that is not labeled for its own page fails,
so a client never opens a wireframe that does not say which page and which device it is.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import REPO_ROOT, resolve_ref

CODE = "AF-LAUNCH-PAGE-DESIGNS"

KINDS = (
    "wireframe_desktop_section", "wireframe_desktop_pdf",
    "wireframe_mobile_section", "wireframe_mobile_pdf",
    "mockup_desktop_section", "mockup_desktop_pdf",
    "mockup_mobile_section", "mockup_mobile_pdf",
    "board",
)
BUILTIN_DELIVERABLES = KINDS
PAGE_TYPES_REF = "49-signature-funnel/structure/page_types.json"

# What the client is told about each approval-gated design. Recorded, never assumed.
APPROVAL_ITEMS = ("design_board", "final_mockups")
APPROVAL_STATES = ("awaiting_client_approval", "approved")

# deliverable_labels.folder(): "<device>-<kind>s"
_FOLDER_KIND = {
    "desktop-wireframes": "wireframe_desktop_section",
    "mobile-wireframes": "wireframe_mobile_section",
    "desktop-mockups": "mockup_desktop_section",
    "mobile-mockups": "mockup_mobile_section",
}
_PDF = re.compile(r"_(DESKTOP|MOBILE)_(WIREFRAMES|MOCKUPS-(?:VISUAL|FINAL))\.pdf$")
_IMAGE = re.compile(r"_(desktop|mobile)_(wireframe|mockup)(?:-(?:visual|final))?_s\d+-of-\d+_", re.I)
_BOARD = re.compile(r"-BOARD\.(?:png|pdf)$", re.I)


def classify(path: str, declared: Optional[str] = None) -> Optional[str]:
    """The deliverable kind of one artifact, or None when it is not a design file."""
    if declared in KINDS:
        return declared
    name = Path(path).name
    m = _PDF.search(name)
    if m:
        return f"{'wireframe' if m.group(2) == 'WIREFRAMES' else 'mockup'}_{m.group(1).lower()}_pdf"
    m = _IMAGE.search(name)
    if m:
        return f"{m.group(2).lower()}_{m.group(1).lower()}_section"
    if _BOARD.search(name):
        return "board"
    parts = Path(path).parts
    for part in parts[:-1]:
        if part in _FOLDER_KIND and name.lower().endswith(".png"):
            return _FOLDER_KIND[part]
    return None


def label_slug(piece: Dict[str, Any]) -> str:
    """The page's slug as Skill 71 names its files: upsell-1, downsell-2, sales-page, landing."""
    instance = piece.get("role_instance")
    if instance == "sales":  # the landing route node's second page; Skill 71 labels it sales_page
        instance = "sales_page"
    role = str(instance or piece.get("role") or "page")
    if not instance and role == "landing" and piece.get("page_kind") == "sales":
        role = "sales_page"
    return re.sub(r"[^a-z0-9]+", "-", role.lower()).strip("-") or "page"


def page_key(piece: Dict[str, Any]) -> str:
    """role plus page kind plus instance: the page's identity everywhere in the package."""
    parts = [str(piece.get("role") or "page")]
    if piece.get("page_kind") and piece["page_kind"] != piece.get("role"):
        parts.append(str(piece["page_kind"]))
    if piece.get("role_instance"):
        parts.append(str(piece["role_instance"]))
    return ":".join(parts)


def load_page_types(root: Optional[Path] = None) -> Tuple[Dict[str, List[str]], str]:
    """({page_key or role: [required kinds]}, source). Never raises: a bad file means the built-in set."""
    try:
        path = resolve_ref(PAGE_TYPES_REF, root or REPO_ROOT)
    except LookupError:
        return {}, "builtin"
    if not path.is_file():
        return {}, "builtin"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, "builtin"
    table = doc.get("pages") or doc.get("page_types") or doc
    if not isinstance(table, dict):
        return {}, "builtin"
    out: Dict[str, List[str]] = {}
    for key, entry in table.items():
        if not isinstance(entry, dict):
            continue
        deliverables = entry.get("deliverables")
        if isinstance(deliverables, dict):
            deliverables = list(deliverables)
        if not isinstance(deliverables, list):
            continue
        kinds = [k for k in deliverables if k in KINDS]
        if kinds:
            out[str(key)] = kinds
            role = entry.get("role")
            if role and role not in out:
                out[str(role)] = kinds
    return out, (f"file:{PAGE_TYPES_REF}" if out else "builtin")


def required_kinds(piece: Dict[str, Any], spec: Dict[str, List[str]]) -> List[str]:
    for key in (page_key(piece), piece.get("role_instance"), piece.get("role")):
        if key and key in spec:
            return spec[key]
    return list(BUILTIN_DELIVERABLES)


def _provider_of(piece: Dict[str, Any], art: Dict[str, Any]) -> Optional[str]:
    return art.get("provider") or piece.get("image_provider")


def design_violations(manifest: Dict[str, Any], root: Path,
                      spec: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """Every way a package's pieces fall short of a full, labeled set of designs. Empty list passes."""
    root = Path(root)
    if spec is None:
        spec, _ = load_page_types()
    fails: List[str] = []
    test_only = bool(manifest.get("test_only"))
    for piece in manifest.get("pieces") or []:
        key = page_key(piece)
        slug = label_slug(piece)
        found: Dict[str, List[str]] = {}
        for art in piece.get("artifacts") or []:
            path = str(art.get("path") or "")
            kind = classify(path, art.get("kind"))
            if kind is None:
                continue
            found.setdefault(kind, []).append(path)
            name = Path(path).name
            if not name.lower().startswith(slug + "_"):
                fails.append(f"{CODE}: {key} file {name!r} is not labeled for this page "
                             f"(a client-facing design file starts with {slug + '_'!r}, then the device and kind)")
            if not (root / path).is_file():
                fails.append(f"{CODE}: {key} {kind} {path!r} does not resolve")
            if (_provider_of(piece, art) == "stub" and kind != "board" and not test_only):
                fails.append(f"{CODE}: {key} {kind} {name!r} was made by the stub provider; "
                             "placeholder pictures are only allowed in a test_only package")
        for kind in required_kinds(piece, spec):
            if kind not in found:
                fails.append(f"{CODE}: {key} is missing {kind.replace('_', ' ')}")
    approvals = manifest.get("design_approvals")
    if not isinstance(approvals, dict):
        fails.append(f"{CODE}: the package does not record the client approval state of the design "
                     "board and the final mockups")
    else:
        for item in APPROVAL_ITEMS:
            entry = approvals.get(item) or {}
            state = entry.get("state")
            if state not in APPROVAL_STATES:
                fails.append(f"{CODE}: {item} approval state is {state!r}; it must be recorded as "
                             f"one of {list(APPROVAL_STATES)}")
            elif state == "approved" and not str(entry.get("approval_ref") or "").strip():
                fails.append(f"{CODE}: {item} is marked approved with no approval reference")
    return fails


def default_approvals() -> Dict[str, Any]:
    """The honest state of a freshly built package: both are waiting for the client."""
    return {item: {"state": "awaiting_client_approval", "approval_ref": None} for item in APPROVAL_ITEMS}
