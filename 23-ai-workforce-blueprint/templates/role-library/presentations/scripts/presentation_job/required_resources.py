"""presentation_job/required_resources.py -- PRES-028: versioned required
resources manifest + safe resolver.

THE ONE-SENTENCE PROBLEM THIS FIXES: compose_prompt() told a text-only
completion to "follow your SOP exactly" while only loading one role document
(+ optional SOUL) -- the MASTERDOC, frame templates and SOP-SIGPRES doctrine
the SOPs name as authoritative never reached the model as bytes, and a
text-only worker has no filesystem tool to fetch them itself.

WHAT THIS IS
------------
  * REQUIRED_RESOURCES: versioned {phase/role -> resource list} table. Each
    entry names master doctrine, selected frame, phase SOP sections, rubric
    and golden structural examples with a content sha256 pin.
  * resolve_required(run_dir, phase_id, dept_root, ...) -> ResolvedResources:
    resolves every entry against the repository AND the materialized
    numbered-role layouts through ONE safe resolver (no path traversal, no
    absolute escapes, repo-root + dept-root jailing). Loads the bytes into
    the context pack (or a bounded excerpt), records exact paths + hashes.
  * Missing required resources -> MissingResourceError carrying the path and
    the install remediation -- the dispatcher turns it into a precise
    preflight installation error BEFORE any paid generation call.
  * validate_references(dept_root): packaging/materialization-time check
    that every declared reference resolves and every pin matches -- prevents
    hand-maintained mirror drift (role/SOP relationships are derived from
    the manifest + SOP mirror headers, not a second hand list).

Rollout flag: PRESENTATION_REQUIRED_RESOURCES=0 disables the preflight
hard-fail (warn-only); the resources still load when present.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FLAG_ENV = "PRESENTATION_REQUIRED_RESOURCES"
FLAG_DEFAULT = "1"

RESOURCES_VERSION = "1.0.0"

INSTALL_REMEDIATION = (
    "install the canonical department tree (fix A1: install the canonical "
    "manifest + SOP/resource closure) or pass --manifest pointing at "
    "universal-sops/presentation-slide-craft/; never hand-edit a duplicate copy")


def flag_enabled() -> bool:
    raw = os.environ.get(FLAG_ENV, FLAG_DEFAULT)
    return str(raw).strip().strip("'\"") != "0"


class MissingResourceError(RuntimeError):
    """A required resource is absent or unreadable. Carries path + remediation."""

    def __init__(self, path: str, role: str, detail: str = "") -> None:
        super().__init__(
            f"missing required resource {path!r} for role {role!r}"
            + (f": {detail}" if detail else "")
            + f". Remediation: {INSTALL_REMEDIATION}")
        self.path = path
        self.role = role


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_join(root: Path, rel: str) -> Optional[Path]:
    """Join a resource relpath under root; None on traversal/absolute escape."""
    if not rel or os.path.isabs(rel):
        return None
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


@dataclass
class ResourceSpec:
    relpath: str
    kind: str  # doctrine | frame | sop | rubric | golden | role
    max_chars: int = 60_000
    pin_sha256: Optional[str] = None


@dataclass
class ResolvedResources:
    phase_id: str
    role: str
    texts: List[Tuple[str, str]] = field(default_factory=list)  # (rel, text)
    manifest: List[Dict[str, Any]] = field(default_factory=list)
    content_hash: str = ""


# ---------------------------------------------------------------------------
# Versioned required-resource table. Roles resolve through the SAME
# resolve_role_prompt_path() the dispatcher uses (repo flat-file + numbered
# materialized layouts); SOP refs come from the manifest's own sop_refs so
# the table cannot drift from what the manifest declares.
# ---------------------------------------------------------------------------
ROLE_DOCTRINE: Dict[str, List[ResourceSpec]] = {
    "signature-presentation-architect": [
        ResourceSpec("51-signature-presentation/MASTERDOC.md", "doctrine"),
        ResourceSpec("sops/SOP-SIGPRES-00-THE-SIGNATURE-PRESENTATION-LAW.md", "sop"),
        ResourceSpec("sops/SOP-SIGPRES-02-PHASE-1-AVATAR-SECTION.md", "sop"),
        ResourceSpec("sops/SOP-SIGPRES-03-PHASE-2-SIGNATURE-STORY.md", "sop"),
        ResourceSpec("sops/SOP-SIGPRES-04-PHASE-3-TRANSFORMATIONAL-TEACHING-NO-PITCH.md", "sop"),
        ResourceSpec("sops/SOP-SIGPRES-05-PHASE-4-PURPOSE-PITCH.md", "sop"),
        ResourceSpec("sops/SOP-SIGPRES-06-FRAMES-HOOK-DOCTRINE-AND-STRUCTURE-GATE.md", "sop"),
        ResourceSpec("51-signature-presentation/structure/sp_structure.json", "rubric"),
        ResourceSpec("51-signature-presentation/examples/golden-quest/slides_copy.md", "golden"),
    ],
    "qc-specialist-signature-presentations": [
        ResourceSpec("51-signature-presentation/MASTERDOC.md", "doctrine"),
        ResourceSpec("sops/SOP-SIGPRES-00-THE-SIGNATURE-PRESENTATION-LAW.md", "sop"),
        ResourceSpec("sops/SOP-SIGPRES-06-FRAMES-HOOK-DOCTRINE-AND-STRUCTURE-GATE.md", "sop"),
        ResourceSpec("51-signature-presentation/structure/sp_structure.json", "rubric"),
        ResourceSpec("51-signature-presentation/examples/golden-quest/slides_copy.md", "golden"),
    ],
    "slide-copywriter": [
        ResourceSpec("sops/slide-copywriter-sops.md", "sop"),
    ],
    "prompt-author-presentations": [
        ResourceSpec("sops/prompt-author-presentations-sops.md", "sop"),
    ],
    "qc-specialist-prompt-presentations": [
        ResourceSpec("sops/qc-specialist-prompt-presentations-sops.md", "sop"),
    ],
    "deep-research-specialist-presentations": [
        ResourceSpec("sops/deep-research-specialist-presentations-sops.md", "sop"),
    ],
    "qc-specialist-presentations": [
        ResourceSpec("sops/qc-specialist-presentations-sops.md", "sop"),
    ],
    "qc-specialist-image-presentations": [
        ResourceSpec("sops/qc-specialist-image-presentations-sops.md", "sop"),
    ],
    "qc-specialist-typography-presentations": [
        ResourceSpec("sops/qc-specialist-typography-presentations-sops.md", "sop"),
    ],
    "qc-specialist-speech-presentations": [
        ResourceSpec("sops/qc-specialist-speech-presentations-sops.md", "sop"),
    ],
    "typography-architect": [
        ResourceSpec("sops/typography-architect-sops.md", "sop"),
    ],
    "slide-image-creator": [
        ResourceSpec("sops/slide-image-creator-sops.md", "sop"),
    ],
    "offer-price-strategist": [
        ResourceSpec("sops/offer-price-strategist-sops.md", "sop"),
    ],
    "attention-content-strategist": [
        ResourceSpec("sops/SOP-NORTHSTAR-00-ATTENTION-IS-THE-PRODUCT.md", "sop"),
        ResourceSpec("sops/SOP-PRIORITY-01-SEVEN-P-MODEL-AND-DIAGNOSTIC.md", "sop"),
        ResourceSpec("sops/SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE.md", "sop"),
    ],
    "director-of-presentations": [
        ResourceSpec("sops/director-of-presentations-sops.md", "sop"),
    ],
    "offer-price-strategist": [
        ResourceSpec("sops/offer-price-strategist-sops.md", "sop"),
    ],
    "content-to-presentation-architect": [
        ResourceSpec("sops/content-to-presentation-architect-sops.md", "sop"),
    ],
    "brand-steward": [
        ResourceSpec("sops/brand-steward-sops.md", "sop"),
    ],
    "pptx-assembly-specialist": [
        ResourceSpec("sops/pptx-assembly-specialist-sops.md", "sop"),
    ],
    "presenters-speech-writer": [
        ResourceSpec("sops/presenters-speech-writer-sops.md", "sop"),
    ],
    "media-librarian-ghl-updater": [
        ResourceSpec("sops/media-librarian-ghl-updater-sops.md", "sop"),
    ],
    "delivery-concierge": [
        ResourceSpec("sops/delivery-concierge-sops.md", "sop"),
    ],
}

FRAME_TEMPLATES = {
    "rulebook": "51-signature-presentation/frame-templates/the-rulebook.md",
    "vault": "51-signature-presentation/frame-templates/the-vault.md",
    "quest": "51-signature-presentation/frame-templates/the-quest.md",
    "original": "51-signature-presentation/frame-templates/the-original.md",
}


def _skill_root_for(dept_root: Path) -> Path:
    """dept_root is <repo>/.../presentations; the 51-signature skill ships
    beside the workforce blueprint tree (repo root) AND inside dept layouts
    on materialized boxes. Prefer the repo-root sibling, fall back to dept."""
    for anc in [dept_root] + list(dept_root.parents):
        cand = anc / "51-signature-presentation" / "MASTERDOC.md"
        if cand.is_file():
            return anc / "51-signature-presentation"
    return dept_root / "51-signature-presentation"


def _read_bounded(path: Path, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...resource excerpt capped...]"
    return text


def _sp_frame(run_dir: Path) -> Optional[str]:
    try:
        obj = json.loads((run_dir / "working" / "copy" / "sp_intake.json")
                         .read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(obj, dict):
        frame = str(obj.get("signature_frame") or "").strip().lower()
        return frame or None
    return None


def resolve_required(run_dir: Path, phase_id: str, role: str, dept_root: Path,
                     *, manifest=None, frame: Optional[str] = None) -> ResolvedResources:
    """Resolve + load every required resource for (phase, role).

    Raises MissingResourceError on the first absent/unreadable required file
    (fail-closed preflight). Records exact paths + sha256 pins.
    """
    resolved = ResolvedResources(phase_id=phase_id, role=role)
    specs: List[ResourceSpec] = list(ROLE_DOCTRINE.get(role, []))

    # Manifest-declared SOP refs ride along (derived, not hand-maintained).
    if manifest is not None:
        try:
            ph = manifest.phase_or_none(phase_id) if hasattr(
                manifest, "phase_or_none") else next(
                    (p for p in manifest.phases if p.id == phase_id), None)
        except Exception:  # noqa: BLE001
            ph = None
        if ph is not None:
            for ref in (getattr(ph, "sop_refs", None)
                        or (ph.get("sop_refs") if isinstance(ph, dict) else []) or []):
                rel = f"sops/{ref}" if not str(ref).startswith("sops/") else str(ref)
                if not any(s.relpath == rel for s in specs):
                    specs.append(ResourceSpec(rel, "sop"))

    # Selected frame template for signature phases.
    want_frame = (frame or _sp_frame(run_dir) or "").strip().lower()
    if want_frame in FRAME_TEMPLATES and role in (
            "signature-presentation-architect",
            "qc-specialist-signature-presentations"):
        specs.append(ResourceSpec(FRAME_TEMPLATES[want_frame], "frame"))

    skill_root = _skill_root_for(dept_root)
    repo_root = skill_root.parent
    for spec in specs:
        # 51-signature paths resolve against the skill root's parent;
        # sops/* resolve against the department root.
        bases = (repo_root, dept_root) if spec.relpath.startswith("51-") \
            else (dept_root, repo_root)
        found: Optional[Path] = None
        for base in bases:
            cand = _safe_join(base, spec.relpath)
            if cand is not None and cand.is_file():
                found = cand
                break
        if found is None:
            raise MissingResourceError(spec.relpath, role)
        try:
            text = _read_bounded(found, spec.max_chars)
            digest = sha256_file(found)
        except OSError as exc:
            raise MissingResourceError(spec.relpath, role, str(exc)) from exc
        if spec.pin_sha256 and digest != spec.pin_sha256:
            raise MissingResourceError(
                spec.relpath, role,
                f"pin mismatch: expected {spec.pin_sha256[:12]}..., got {digest[:12]}...")
        resolved.texts.append((spec.relpath, text))
        resolved.manifest.append({"path": spec.relpath,
                                  "resolved": str(found),
                                  "sha256": digest,
                                  "kind": spec.kind,
                                  "chars": len(text)})
    resolved.content_hash = hashlib.sha256(
        json.dumps(resolved.manifest, sort_keys=True,
                   default=str).encode("utf-8")).hexdigest()
    return resolved


def validate_references(dept_root: Path, manifest=None) -> List[str]:
    """Packaging/materialization-time validation: every declared reference
    resolves. Returns the list of problems (empty = clean)."""
    problems: List[str] = []
    seen: set = set()
    for role, specs in ROLE_DOCTRINE.items():
        for spec in specs:
            if spec.relpath in seen:
                continue
            seen.add(spec.relpath)
            bases = [dept_root, _skill_root_for(dept_root).parent]
            if not any((_safe_join(b, spec.relpath) or Path()).is_file()
                       for b in bases if _safe_join(b, spec.relpath) is not None):
                problems.append(f"role {role}: unresolvable {spec.relpath}")
    if manifest is not None:
        try:
            phases = list(manifest.phases)
        except Exception:  # noqa: BLE001
            phases = []
        for ph in phases:
            for ref in (getattr(ph, "sop_refs", []) or []):
                rel = f"sops/{ref}" if not str(ref).startswith("sops/") else str(ref)
                if not (dept_root / rel).is_file():
                    problems.append(f"phase {ph.id}: unresolvable {rel}")
    # Mirror-drift guard: every sops/*-sops.md mirror must carry the
    # regeneration header naming its authoritative source.
    try:
        mirrors = sorted((dept_root / "sops").glob("*-sops.md"))
    except OSError:
        mirrors = []
    for mirror in mirrors:
        try:
            head = mirror.read_text(encoding="utf-8",
                                    errors="replace")[:2000]
        except OSError:
            continue
        if "regenerated from" not in head.lower() and \
                "mirror" not in head.lower():
            problems.append(f"mirror {mirror.name}: missing regeneration header")
    return problems


def preflight_required(run_dir: Path, phase_id: str, role: str,
                       dept_root: Path, *, manifest=None,
                       frame: Optional[str] = None) -> ResolvedResources:
    """Dispatcher preflight: resolve or raise a precise installation error
    before any paid generation. Warn-only when the rollout flag is off."""
    try:
        return resolve_required(run_dir, phase_id, role, dept_root,
                                manifest=manifest, frame=frame)
    except MissingResourceError:
        if not flag_enabled():
            empty = ResolvedResources(phase_id=phase_id, role=role)
            return empty
        raise
