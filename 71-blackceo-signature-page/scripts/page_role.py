#!/usr/bin/env python3
"""page_role.py - the canonical section sequence of every page type Skill 71 draws.

The landing page has two canonical forms (Standard 12 sections, Long-Form 15), each a
copy spec in references/copy-specs/. Every other page type of the funnel (the
thank-you page today) has its own spec in the same directory, in the same shape,
carrying one extra key, `page_role`, that names the funnel role it serves. This module
is the one place that maps a role or a copy version to its spec, so the section-count
check, the request builder, the wireframe prompt, the Design Board and the gate all read
the same file and nothing forks the pipeline.

A spec without `page_role` is a landing form. A page role with no spec yet (for example
product_selection) keeps its legacy behaviour: it resolves to None here and the callers
fall through to the landing path, exactly as before.

Library only; it calls no provider and reads no secret.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import copy_forms  # noqa: E402  the one registry of copy forms

SKILL_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = SKILL_ROOT / "references" / "copy-specs"
LANDING_VERSIONS = ("standard", "long-form")
LANDING_ROLE = "landing"
MOBILE_MAX_WIDTH = 768


@lru_cache(maxsize=None)
def _read(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _owns_wireframe_wording(spec) -> bool:
    """A page type whose spec carries its own wireframe wording (`wireframe.form_label`, the
    thank-you page). A registered form that only names a page_role (product-selection, in
    copy_forms.py) is drawn from the shared form wording instead and keeps its own path."""
    wireframe = spec.get("wireframe") if isinstance(spec.get("wireframe"), dict) else {}
    return bool(wireframe.get("form_label"))


def role_specs() -> dict:
    """{copy_version: spec} for every spec in references/copy-specs/ that names a page_role and
    owns its wireframe wording."""
    out = {}
    for path in sorted(SPEC_DIR.glob("*.json")):
        try:
            spec = _read(str(path))
        except (OSError, ValueError):
            continue
        if (isinstance(spec, dict) and spec.get("page_role") and spec.get("copy_version")
                and _owns_wireframe_wording(spec)):
            out[str(spec["copy_version"])] = spec
    return out


def copy_versions() -> tuple:
    """Every copy_version a run may declare: the landing forms, then each page role's own."""
    return LANDING_VERSIONS + tuple(role_specs())


def load_spec(version):
    """The spec for a declared copy_version, or None when it is not one this skill knows."""
    if version in LANDING_VERSIONS:
        return _read(str(SPEC_DIR / f"{version}-v6.json"))
    return role_specs().get(str(version))


def spec_ref(version) -> str:
    """The spec's path relative to the skill root, as the stage contract's validator commands
    name it (references/copy-specs/<file>); '' when the version is unknown."""
    if version in LANDING_VERSIONS:
        return f"references/copy-specs/{version}-v6.json"
    for path in sorted(SPEC_DIR.glob("*.json")):
        spec = _read(str(path))
        if isinstance(spec, dict) and spec.get("page_role") and spec.get("copy_version") == version:
            return f"references/copy-specs/{path.name}"
    return ""


def spec_for_role(role):
    """The role's own spec, or None (landing, or a role with no section structure yet)."""
    for spec in role_specs().values():
        if spec["page_role"] == role:
            return spec
    return None


def _json(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def declared_role(run_dir, request=None) -> str:
    """The run's page role: the request, its metadata, intake.json (top level, then the
    launch block), page-request.json, then the role of a declared role copy_version, else
    landing. The first declaration wins."""
    request = request if isinstance(request, dict) else {}
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    intake = _json(Path(run_dir) / "intake.json") or {}
    launch = intake.get("launch") if isinstance(intake.get("launch"), dict) else {}
    page_request = _json(Path(run_dir) / "page-request.json") or {}
    for value in (request.get("page_role"), metadata.get("page_role"), intake.get("page_role"),
                  launch.get("page_role"), page_request.get("page_role")):
        if isinstance(value, str) and value:
            return value
    for value in (request.get("copy_version"), metadata.get("copy_version"),
                  intake.get("copy_version")):
        form = copy_forms.norm(value) if value else None  # a registered form names its own role
        role = copy_forms.load_spec(form).get("page_role") if form else None
        if role:
            return role
    return LANDING_ROLE


def request_spec(request):
    """The role spec a loaded production request is drawn against, or None for a landing
    request. stage_executor.load_request stamps `page_role` into every request."""
    request = request if isinstance(request, dict) else {}
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    spec = spec_for_role(request.get("page_role") or metadata.get("page_role"))
    if spec is None:
        spec = role_specs().get(str(request.get("copy_version") or metadata.get("copy_version")))
    return spec


def section_spec(spec, section_id):
    """The spec's section entry for a request section id ("S02", "2" and "02" are the same)."""
    want = str(section_id or "").strip().upper().lstrip("S").lstrip("0")
    return next((s for s in spec["sections"] if str(s["id"]).upper() == want), None)


def layout_block(stage, section, request, width) -> str:
    """The page type's structure for one section slice, for every stage that draws it
    (both wireframes and both mockups): '' for a landing request. Structure only; colour,
    type and image rules come from the stage's own blocks, never from here."""
    spec = request_spec(request)
    entry = section_spec(spec, section.get("section_id")) if spec else None
    if not entry or not entry.get("layout"):
        return ""
    platform = "mobile" if width <= MOBILE_MAX_WIDTH else "desktop"
    rules = spec.get("rules") or {}
    return (f"PAGE TYPE STRUCTURE — this is the {spec['page_label']} ({len(spec['sequence'])} sections), "
            f"section {section['section_id']} of {len(spec['sequence'])}, {entry['name']}. "
            f"{platform.capitalize()} layout: {entry['layout'][platform]} "
            f"The whole page carries {rules.get('max_images', 0)} "
            f"image{'' if rules.get('max_images') == 1 else 's'} in total and no offer "
            "button; every button on it is a utility button.")


if __name__ == "__main__":
    raise SystemExit("page_role.py is a library; see scripts/stage_executor.py --preflight")
