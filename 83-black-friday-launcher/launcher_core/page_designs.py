"""AF-LAUNCH-PAGE-DESIGNS: every page of a launch ships its full set of designs, clearly labeled.

A package that holds a page without its desktop AND mobile wireframes and mockups, the two combined
review PDFs per kind, the overview boards and the clear labels is not a delivered package, however
many hashes match. This module knows what "a full set" is and reads it from one place:

* ``49-signature-funnel/structure/page_types.json`` (contract C2) when it exists, so a page type
  added there is required here with no code change;
* otherwise the built-in set below, recorded as ``source: "builtin"`` so the report says so.

Deliverable kinds are inferred from the file names Skill 71's ``deliverable_labels.py`` produces; a
``kind`` an artifact declares for itself is never believed. Only MOCKUPS-FINAL files are mockups (the
VISUAL layout proof is not). A file that is not labeled for its own page fails, so a client never
opens a wireframe that does not say which page and which device it is.

A client delivery (``test_only`` false) also needs real files: a PNG or PDF by its magic bytes with
nonzero dimensions, found in a closed Skill 71 ``stage_gate`` run (the piece's ``stage_state``: the
run's ``private/state.json`` copied into the package, hash recorded), and an ``approved`` design
approval that resolves to a Skill 71 Design Board production record whose hash is checked.

WHAT MAKES A SET COMPLETE (F17). Completeness is proved per INSTANCE, never by a role or a count:

* a design file with no recorded image provider is refused outright (provider unknown), so the
  placeholder rule can never be skipped by leaving the provider out;
* the page set is the launch's (``route-graph.json``), so a page the launch plans and the package
  does not carry is named missing, and a piece the launch did not plan is named unexpected;
* every section image is bound by its own path AND hash to the closed stage that produced it, so a
  duplicate reference cannot stand in for a missing section and a layout proof cannot be retitled
  as the final mockup (or the reverse) — the two are different stages' artifacts;
* each section image's own label carries its page slug, its device and its ``sNN-of-MM`` section
  identity; the devices and section numbers are checked against the page type, and the same section
  number twice is refused;
* one page's ``stage_state`` receipt is one page instance's receipt: two pieces cannot share it,
  and two pieces cannot claim one planned instance.
"""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .constants import REPO_ROOT, resolve_ref
from . import section_structure

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
_FOLDER_KIND = {  # wireframes only: both mockup stages share one folder, so a folder never proves FINAL
    "desktop-wireframes": "wireframe_desktop_section",
    "mobile-wireframes": "wireframe_mobile_section",
}
_PDF = re.compile(r"_(DESKTOP|MOBILE)_(WIREFRAMES|MOCKUPS-FINAL)\.pdf$")
_IMAGE = re.compile(r"_(desktop|mobile)_(wireframe|mockup(?:-visual|-final)?)_s(\d+)-of-(\d+)_", re.I)
_BOARD = re.compile(r"-BOARD\.(?:png|pdf)$", re.I)
ROUTE_GRAPH_REL = "route-graph.json"


def classify(path: str, declared: Optional[str] = None) -> Optional[str]:
    """The deliverable kind of one artifact, or None when it is not a design file.

    ``declared`` is accepted for old callers and ignored: a file is what its name says it is.
    """
    name = Path(path).name
    m = _PDF.search(name)
    if m:
        return f"{'wireframe' if m.group(2) == 'WIREFRAMES' else 'mockup'}_{m.group(1).lower()}_pdf"
    m = _IMAGE.search(name)
    if m:
        what = m.group(2).lower()
        if what == "mockup" or what.endswith("-visual"):  # layout proof, or no stage named: not final
            return None
        return f"{what.split('-')[0]}_{m.group(1).lower()}_section"
    if _BOARD.search(name):
        return "board"
    for part in Path(path).parts[:-1]:
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


class PageTypesError(ValueError):
    """page_types.json exists but cannot be used. The check never falls back to the built-in set then."""


# page_types.json top-level `deliverables[].id` -> the kind this module checks
_DELIVERABLE_KIND = {
    "desktop_wireframe_sections": "wireframe_desktop_section", "mobile_wireframe_sections": "wireframe_mobile_section",
    "desktop_mockup_sections": "mockup_desktop_section", "mobile_mockup_sections": "mockup_mobile_section",
    "desktop_wireframe_pdf": "wireframe_desktop_pdf", "mobile_wireframe_pdf": "wireframe_mobile_pdf",
    "desktop_mockup_pdf": "mockup_desktop_pdf", "mobile_mockup_pdf": "mockup_mobile_pdf",
    "overview_boards": "board",
}
DEFAULT_KEY = "*"  # load_page_types(): the top-level deliverables, for every page without its own list


def _page_types_doc(root: Optional[Path] = None) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
    """(document, path) when the contract file exists; (None, None) when it does not. A file that is
    there but unreadable raises: a broken contract is never treated as an absent one."""
    try:
        path = resolve_ref(PAGE_TYPES_REF, root or REPO_ROOT)
    except LookupError:
        return None, None
    if not path.is_file():
        return None, None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PageTypesError(f"{PAGE_TYPES_REF} exists but cannot be read ({exc.__class__.__name__})") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("pages"), dict):
        raise PageTypesError(f"{PAGE_TYPES_REF} exists but has no 'pages' table")
    return doc, path


def _kinds_of(deliverables: Any) -> List[str]:
    """Kinds named by a deliverables list: kind names, ids, or {id|kind: ...} entries."""
    if isinstance(deliverables, dict):
        deliverables = list(deliverables)
    kinds: List[str] = []
    for item in deliverables if isinstance(deliverables, list) else []:
        name = item.get("id") or item.get("kind") if isinstance(item, dict) else item
        kind = name if name in KINDS else _DELIVERABLE_KIND.get(name)
        if kind and kind not in kinds:
            kinds.append(kind)
    return kinds


def load_page_types(root: Optional[Path] = None) -> Tuple[Dict[str, List[str]], str]:
    """({page_key or role: [required kinds]}, source).

    No contract file: ({}, "builtin"). A file: every page gets its own ``deliverables`` when it has
    them, else the top-level ``deliverables`` list (also under the key ``*``); the source is
    ``file:<ref>``. A file that exists but cannot be used raises PageTypesError.
    """
    doc, _ = _page_types_doc(root)
    if doc is None:
        return {}, "builtin"
    default = _kinds_of(doc.get("deliverables"))
    out: Dict[str, List[str]] = {DEFAULT_KEY: default} if default else {}
    for key, entry in doc["pages"].items():
        if not isinstance(entry, dict):
            continue
        kinds = _kinds_of(entry.get("deliverables")) or default
        if kinds:
            out[str(key)] = kinds
            role = entry.get("role")
            if role and role not in out:
                out[str(role)] = kinds
    if not out:
        raise PageTypesError(f"{PAGE_TYPES_REF} exists but names no deliverable kind this check knows")
    return out, f"file:{PAGE_TYPES_REF}"


def load_page_rules(root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """{page key: {"sections": {allowed counts}, "design_only": bool}} from the contract file's pages table."""
    doc, _ = _page_types_doc(root)
    rules: Dict[str, Dict[str, Any]] = {}
    for key, entry in ((doc or {}).get("pages") or {}).items():
        if isinstance(entry, dict):
            counts = {n for n in (entry.get("sections"), entry.get("long_form_sections"))
                      if isinstance(n, int) and not isinstance(n, bool)}
            rules[str(key)] = {"sections": counts, "design_only": bool(entry.get("design_only"))}
    return rules


def declared_page_keys(root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """{page key: page type entry} from the contract file: every page identity the funnel can build."""
    doc, _ = _page_types_doc(root)
    return {str(k): v for k, v in ((doc or {}).get("pages") or {}).items() if isinstance(v, dict)}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def planned_instances(root: Path) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """(the page instances the LAUNCH planned, why-not) from the package's own route graph.

    A directory of pieces answers "what was delivered"; the route graph answers "what was planned".
    The two are different questions, and only the second can name a page missing.
    """
    doc = _read_json(Path(root) / ROUTE_GRAPH_REL)
    if not isinstance(doc, dict) or not isinstance(doc.get("nodes"), list) or not doc["nodes"]:
        return None, f"the package carries no {ROUTE_GRAPH_REL}, so the planned page set is unknown"
    out: List[Dict[str, Any]] = []
    for node in doc["nodes"]:
        if not isinstance(node, dict) or not node.get("role"):
            continue
        role = str(node["role"])
        key = role
        if node.get("page_kind") and str(node["page_kind"]) != role:
            key += f":{node['page_kind']}"
        if node.get("role_instance"):
            key += f":{node['role_instance']}"
        out.append({"key": key, "role": role, "page_kind": node.get("page_kind"),
                    "role_instance": node.get("role_instance"), "page_id": node.get("page_id")})
    return (out, f"{ROUTE_GRAPH_REL} ({len(out)} planned page(s))") if out else (None, f"{ROUTE_GRAPH_REL} plans no page")


def required_kinds(piece: Dict[str, Any], spec: Dict[str, List[str]]) -> List[str]:
    for key in (page_key(piece), piece.get("role_instance"), piece.get("role"), DEFAULT_KEY):
        if key and key in spec:
            return spec[key]
    return list(BUILTIN_DELIVERABLES)


def _provider_of(piece: Dict[str, Any], art: Dict[str, Any]) -> Optional[str]:
    return art.get("provider") or piece.get("image_provider")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- real files

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MEDIABOX = re.compile(rb"/MediaBox\s*\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\]")


def real_file_problem(path: Path, kind: str, strict: bool = True) -> Optional[str]:
    """Why this file is not a real picture or document of its kind, or None. PNG: magic bytes, an IHDR
    with nonzero width and height, a closing IEND. PDF: the %PDF- header always; when strict also an
    end marker and a page box with nonzero width and height."""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            head = fh.read(24)
            fh.seek(max(0, size - 16))
            tail = fh.read(16)
    except OSError as exc:
        return f"cannot be read ({exc.__class__.__name__})"
    if kind.endswith("_pdf") or (kind == "board" and head.startswith(b"%PDF-")):
        if not head.startswith(b"%PDF-"):
            return "is not a PDF (no %PDF- header)"
        if not strict:
            return None
        data = path.read_bytes()
        if b"%%EOF" not in data[-2048:]:
            return "is a truncated PDF (no end marker)"
        boxes = [(float(m.group(3)) - float(m.group(1)), float(m.group(4)) - float(m.group(2)))
                 for m in _MEDIABOX.finditer(data)]
        if not any(w > 0 and h > 0 for w, h in boxes):
            return "is a PDF with no page of nonzero size"
        return None
    if not head.startswith(_PNG_MAGIC) or head[12:16] != b"IHDR":
        return "is not a PNG (no PNG signature and header)"
    if int.from_bytes(head[16:20], "big") <= 0 or int.from_bytes(head[20:24], "big") <= 0:
        return "is a PNG with zero width or height"
    if b"IEND" not in tail:
        return "is a truncated PNG (no IEND)"
    return None


# ---------------------------------------------------------------- stage_gate evidence

# The Skill 71 stages whose closed run may have produced each kind (stage-contract.json names)
_STAGES_FOR = {
    "wireframe_desktop": ("desktop-wireframe",), "wireframe_mobile": ("mobile-tablet",),
    "mockup_desktop": ("final-mockups",), "mockup_mobile": ("final-mockups",),
    "board": ("final-mockups", "design-board"),
}


def _inside(root: Path, rel: Any) -> Optional[Path]:
    """root/rel when it stays inside root, else None."""
    if not isinstance(rel, str) or not rel.strip():
        return None
    target = (root / rel).resolve()
    return target if target.is_relative_to(root.resolve()) else None


def section_identity(path: str) -> Optional[Dict[str, Any]]:
    """A section image's own identity from its label: device, kind, section number and total.

    ``upsell-1_desktop_wireframe_s03-of-08_offer.png`` is section 3 of 8, desktop, wireframe. The
    label Skill 71 writes is the only place a section states its identity, so this reads it rather
    than trusting a position in a list or a count.
    """
    match = _IMAGE.search(Path(path).name)
    if not match:
        return None
    return {"device": match.group(1).lower(), "kind": match.group(2).lower(),
            "section": int(match.group(3)), "of": int(match.group(4))}


def load_stage_state(piece: Dict[str, Any], root: Path) -> Tuple[Optional[Dict[str, Dict[str, str]]], str]:
    """({closed stage: {artifact path: sha256 recorded at close}}, "") or (None, why).

    The piece's ``stage_state`` is {"path", "sha256"}: the run's private/state.json copied into the
    package. Only a stage with status closed and receipt_status pass counts as closed. The map is
    PATH -> HASH (never a bare hash set): a file is bound to the stage that produced it by its own
    path, so two files that happen to share bytes cannot vouch for each other.
    """
    ref = piece.get("stage_state")
    if not isinstance(ref, dict):
        return None, "carries no stage_state (the stage_gate run state its files came from)"
    path = _inside(root, ref.get("path"))
    if path is None or not path.is_file():
        return None, f"stage_state {ref.get('path')!r} does not resolve inside the package"
    if _sha256(path) != ref.get("sha256"):
        return None, "stage_state does not match its recorded hash"
    try:
        stages = (json.loads(path.read_text(encoding="utf-8")) or {}).get("stages")
    except (OSError, ValueError):
        return None, "stage_state is not readable JSON"
    if not isinstance(stages, dict):
        return None, "stage_state has no stages"
    closed: Dict[str, Dict[str, str]] = {}
    for name, entry in stages.items():
        if isinstance(entry, dict) and entry.get("status") == "closed" and entry.get("receipt_status") == "pass":
            hashes = entry.get("artifact_hashes")
            closed[name] = {str(rel): str(digest) for rel, digest in hashes.items()
                            } if isinstance(hashes, dict) else {}
    return closed, ""


def _evidence_problem(kind: str, path: str, digest: str,
                      closed: Dict[str, Dict[str, str]]) -> Optional[str]:
    stages = _STAGES_FOR.get(kind.rsplit("_", 1)[0], _STAGES_FOR["board"])
    live = [s for s in stages if s in closed]
    if not live:
        return f"comes from no closed {' or '.join(stages)} stage"
    # The stage contract hashes section PNGs by path; the review PDFs and boards are proven by
    # their stage closing. A section file is among ITS stage's recorded files only when the file's
    # own path carries the hash recorded at close: a look-alike path, or another stage's file with
    # the same bytes (a layout proof retitled as the final mockup), is not evidence.
    if kind.endswith("_section"):
        recorded = [closed.get(s, {}).get(path) for s in live]
        if digest not in [d for d in recorded if d]:
            return f"is not among the files the closed {live[0]} stage recorded"
    return None


# ---------------------------------------------------------------- approvals

def approval_record_problem(entry: Dict[str, Any], root: Path) -> Optional[str]:
    """Why an approved entry's ``approval_ref`` is not a recorded Design Board approval, or None.

    ``approval_ref`` names a Skill 71 design-board production record (relative to the package, or an
    absolute path); ``record_sha256`` is that file's hash. The record must carry a client approval
    made by the platform path: decision approved, party client, a hashed evidence record, and the
    hashes of the board it approved (matched against the board beside the record when present).
    """
    ref = str(entry.get("approval_ref") or "").strip()
    path = Path(ref) if Path(ref).is_absolute() else _inside(root, ref)
    if path is None or not path.is_file():
        return f"approval reference {ref!r} does not resolve to a recorded Design Board approval"
    if _sha256(path) != entry.get("record_sha256"):
        return f"approval reference {ref!r} does not match its recorded hash (record_sha256)"
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"approval reference {ref!r} is not a readable design board record"
    ap = rec.get("approval") if isinstance(rec, dict) else None
    if not isinstance(rec, dict) or rec.get("artifact") != "design-board" or not isinstance(ap, dict):
        return f"approval reference {ref!r} is not a design board record with an approval"
    if ap.get("decision") != "approved" or ap.get("party") != "client":
        return f"approval reference {ref!r} records no client approval"
    for key in ("approved_by", "evidence_ref", "evidence_sha256", "evidence_message_id", "approved_at"):
        if not str(ap.get(key) or "").strip():
            return f"approval reference {ref!r} lacks {key} (the client's own recorded message)"
    board = (rec.get("board") or {}).get("sha256")
    bound = {"board_sha256": board, "image_set_sha256": (rec.get("image_set") or {}).get("sha256"),
             "palette_sha256": rec.get("palette_sha256"), "page_role": rec.get("page_role")}
    stale = [k for k, v in bound.items() if not v or ap.get(k) != v]
    if stale:
        return f"approval reference {ref!r} is stale: the board changed after approval ({', '.join(stale)})"
    shown = path.parent / Path(str((rec.get("board") or {}).get("file") or "")).name
    if shown.is_file() and _sha256(shown) != board:
        return f"approval reference {ref!r}: the board image beside it is not the board that was approved"
    return None


def approval_violations(approvals: Any, root: Path) -> List[str]:
    """Violations in a manifest's design_approvals; also what `assemble --design-approvals` checks."""
    if not isinstance(approvals, dict):
        return [f"{CODE}: the package does not record the client approval state of the design "
                "board and the final mockups"]
    fails: List[str] = []
    for item in APPROVAL_ITEMS:
        entry = approvals.get(item) or {}
        state = entry.get("state")
        if state not in APPROVAL_STATES:
            fails.append(f"{CODE}: {item} approval state is {state!r}; it must be recorded as "
                         f"one of {list(APPROVAL_STATES)}")
        elif state == "approved":
            if not str(entry.get("approval_ref") or "").strip():
                fails.append(f"{CODE}: {item} is marked approved with no approval reference")
            else:
                problem = approval_record_problem(entry, Path(root))
                if problem:
                    fails.append(f"{CODE}: {item} is marked approved but {problem}")
    return fails


# ---------------------------------------------------------------- the check

def _section_rule(piece: Dict[str, Any], rules: Dict[str, Dict[str, Any]]) -> Optional[Set[int]]:
    keys = [page_key(piece), piece.get("role_instance"), piece.get("role")]
    if label_slug(piece) == "sales-page":
        keys.insert(0, "sales")
    for key in keys:
        if key and key in rules and rules[key]["sections"]:
            return rules[key]["sections"]
    return None


def design_violations(manifest: Dict[str, Any], root: Path,
                      spec: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """Every way a package's pieces fall short of a full, labeled set of designs. Empty list passes."""
    root = Path(root)
    if spec is None:
        try:
            spec, _ = load_page_types()
        except PageTypesError as exc:
            return [f"{CODE}: {exc}; the built-in set is not used in its place"]
    try:
        rules = load_page_rules()
    except PageTypesError:
        rules = {}
    fails: List[str] = []
    test_only = bool(manifest.get("test_only"))
    pieces = [p for p in (manifest.get("pieces") or []) if isinstance(p, dict)]
    planned, planned_why = planned_instances(root)
    if planned is not None:
        fails.extend(_instance_violations(pieces, planned))
    receipts: Dict[Tuple[str, str], List[str]] = {}   # (path, sha) -> the page keys claiming it
    for piece in pieces:
        key = page_key(piece)
        slug = label_slug(piece)
        found: Dict[str, List[str]] = {}
        closed: Optional[Dict[str, Dict[str, str]]] = None
        if not test_only:
            closed, why = load_stage_state(piece, root)
            if closed is None:
                fails.append(f"{CODE}: {key} {why}; a client delivery needs a closed stage_gate run")
            else:
                ref = piece["stage_state"]
                receipts.setdefault((str(ref.get("path")), str(ref.get("sha256"))), []).append(key)
        seen: Set[str] = set()
        for art in piece.get("artifacts") or []:
            path = str(art.get("path") or "")
            kind = classify(path)
            if kind is None:
                continue
            if path in seen:  # the same reference twice cannot be two sections or two kinds
                fails.append(f"{CODE}: {key} lists {Path(path).name!r} twice; a duplicate reference "
                             "cannot stand in for another section")
                continue
            seen.add(path)
            found.setdefault(kind, []).append(path)
            name = Path(path).name
            if not name.lower().startswith(slug + "_"):
                fails.append(f"{CODE}: {key} file {name!r} is not labeled for this page "
                             f"(a client-facing design file starts with {slug + '_'!r}, then the device and kind)")
            identity = section_identity(path)
            if identity and kind.endswith("_section") and identity["device"] != kind.split("_")[1]:
                fails.append(f"{CODE}: {key} {kind} {name!r} is drawn at {identity['device']} but labeled as a "
                             f"{kind.split('_')[1]} section; viewport identity is part of the deliverable")
            target = root / path
            if not target.is_file():
                fails.append(f"{CODE}: {key} {kind} {path!r} does not resolve")
            else:
                digest = _sha256(target)
                problem = real_file_problem(target, kind, strict=not test_only)
                if art.get("sha256") and art["sha256"] != digest:
                    problem = "does not match its recorded hash"
                if problem is None and closed is not None:
                    problem = _evidence_problem(kind, path, digest, closed)
                if problem:
                    fails.append(f"{CODE}: {key} {kind} {name!r} {problem}")
            provider = _provider_of(piece, art)
            if provider == "stub" and kind != "board" and not test_only:
                fails.append(f"{CODE}: {key} {kind} {name!r} was made by the stub provider; "
                             "placeholder pictures are only allowed in a test_only package")
            elif not provider and kind != "board" and not test_only:
                # UPS-23 / issue 16: the stub rule above can only fire when a provider is named, so a
                # design file that names none (the upsell pages' results used to carry none) is a
                # finding, never a pass: nobody can tell a placeholder from a real render.
                fails.append(f"{CODE}: {key} {kind} {name!r} names no image provider (provider unknown); "
                             "a client delivery must say which provider drew each design file, so the "
                             "placeholder rule can be applied")
        for kind in required_kinds(piece, spec):
            if kind not in found:
                fails.append(f"{CODE}: {key} is missing {kind.replace('_', ' ')}")
        fails.extend(_section_identity_violations(key, found))
        if not test_only:
            # F17 item 5: the sections a page must carry are ITS role's own structure, resolved from
            # Skill 71's routing (page-structures.json, role_spec, copy_forms, page-kinds) — never the
            # main sales-page skeleton applied to every role.
            fails.extend(section_structure.section_problems(piece, key, found, section_identity))
        allowed = None if test_only else _section_rule(piece, rules)
        if allowed:
            counts = {k: len(v) for k, v in found.items() if k.endswith("_section")}
            for kind, n in sorted(counts.items()):
                if n not in allowed or len(set(counts.values())) > 1:
                    fails.append(f"{CODE}: {key} has {n} {kind.replace('_', ' ')} images; "
                                 f"its page type has {sorted(allowed)} sections")
    for (path, digest), holders in sorted(receipts.items()):
        if len(set(holders)) > 1:
            fails.append(f"{CODE}: {' and '.join(sorted(set(holders)))} cite the same stage_gate receipt "
                         f"({Path(path).name}, attempt/input revision {digest[:12]}); one page's run receipt "
                         "is one page instance's receipt")
    fails.extend(approval_violations(manifest.get("design_approvals"), root))
    return fails


def _section_identity_violations(key: str, found: Dict[str, List[str]]) -> List[str]:
    """Each section image's own section number, once, per kind: a count is never a section identity."""
    fails: List[str] = []
    for kind, paths in sorted(found.items()):
        if not kind.endswith("_section"):
            continue
        numbers: List[int] = []
        for path in paths:
            identity = section_identity(path)
            if identity is None:
                fails.append(f"{CODE}: {key} {kind} {Path(path).name!r} carries no sNN-of-MM section identity; "
                             "the label is how a section states which section it is")
                continue
            numbers.append(identity["section"])
        repeated = sorted({n for n in numbers if numbers.count(n) > 1})
        if repeated:
            fails.append(f"{CODE}: {key} {kind.replace('_', ' ')} carries section {repeated[0]} more than once; "
                         "a duplicate section cannot stand in for a missing one")
    return fails


def _instance_violations(pieces: List[Dict[str, Any]],
                         planned: List[Dict[str, Any]]) -> List[str]:
    """Every planned page instance has exactly one piece, and no piece is a page never planned.

    Instances are matched by their own key first (landing:opt_in and landing:sales are two pages,
    and each needs its own piece). A planned key that names only a role — a route node with no
    page kind — is satisfied by any piece of that role, because the launch has not split the role.
    One piece can therefore never stand in for two planned instances of one role.
    """
    fails: List[str] = []
    declared = declared_page_keys()
    planned_keys = [p["key"] for p in planned]
    planned_roles = {p["role"] for p in planned}
    piece_keys = [page_key(piece) for piece in pieces]
    keys: Dict[str, int] = {}
    for key in piece_keys:
        keys[key] = keys.get(key, 0) + 1
    for piece, key in zip(pieces, piece_keys):
        role = str(piece.get("role") or "")
        if role not in planned_roles:
            fails.append(f"{CODE}: {key} is not a page the launch plans "
                         f"(planned roles: {', '.join(sorted(planned_roles))})")
            continue
        if declared and key not in declared and role not in declared:
            fails.append(f"{CODE}: {key} is not a page type Skill 49's inventory declares")
    for want in planned_keys:
        if want in keys:
            continue
        role = want.split(":")[0]
        if want == role and role in {k.split(":")[0] for k in keys}:
            continue  # a role-level plan node, satisfied by that role's piece(s)
        fails.append(f"{CODE}: {want} is planned and has no piece (no design set is recorded for it)")
    for key, n in sorted(keys.items()):
        if n > 1:
            fails.append(f"{CODE}: {n} pieces claim the page instance {key}; each planned page gets its own chain")
    return fails


def default_approvals() -> Dict[str, Any]:
    """The honest state of a freshly built package: both are waiting for the client."""
    return {item: {"state": "awaiting_client_approval", "approval_ref": None} for item in APPROVAL_ITEMS}
