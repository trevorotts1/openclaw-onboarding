#!/usr/bin/env python3
"""page_role.py - the canonical section sequence of every page type Skill 71 draws.

The landing page has two canonical forms (Standard 12 sections, Long-Form 15), each a
copy spec in references/copy-specs/. Every other page type of the funnel (the
thank-you page today) has its own spec in the same directory, in the same shape,
carrying one extra key, `page_role`, that names the funnel role it serves. This module
is the one place that maps a role or a copy version to its spec, so the section-count
check, the request builder, the wireframe prompt, the Design Board and the gate all read
the same file and nothing forks the pipeline.

A spec without `page_role`/`page_roles` is a landing form. FIX-07: the page-role vocabulary
is the route-graph schema's closed enum, read at runtime by validate_page_role, and a role
the schema does not permit raises PageRoleUnknown naming the token. FIX-15: discovery is recursive
under references/copy-specs/ (checkout lives at roles/checkout.json), is keyed by the role or
version the spec itself declares, and never uses `wireframe.form_label` as an existence
filter. A role that has a spec file on disk but is missing from discovery fails closed with
RoleSpecNotDiscovered rather than resolving to None.

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
# FIX-07: the authoritative page-role vocabulary is the closed enum the route graph emits,
# read from the schema at runtime. Never a hand-maintained copy in this module.
ROUTE_GRAPH_SCHEMA = SKILL_ROOT.parent / "49-signature-funnel" / "schema" / "route-graph.schema.json"
# The per-role section structure registry (downsell_1 lives here, not in a copy spec).
PAGE_STRUCTURES = SKILL_ROOT / "references" / "page-structures.json"
LANDING_VERSIONS = ("standard", "long-form")
LANDING_ROLE = "landing"
MOBILE_MAX_WIDTH = 768


@lru_cache(maxsize=None)
def _read(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class RoleSpecNotDiscovered(LookupError):
    """A role has a spec file on disk but discovery did not return it (FIX-15: fail closed)."""


class PageRoleSchemaUnavailable(RuntimeError):
    """The route-graph schema that owns the page-role vocabulary cannot be read (fail closed)."""


class PageRoleUnknown(LookupError):
    """A page role the route-graph schema does not permit (FIX-07: a specific diagnostic)."""


class PageRoleUnregistered(LookupError):
    """A schema role with no copy spec, page structure or registered form (FIX-07 coverage)."""


@lru_cache(maxsize=None)
def schema_page_roles() -> tuple:
    """The page-role enum read from 49-signature-funnel/schema/route-graph.schema.json.

    The schema is the authority the route graph emits, so the validator reads it instead of
    holding a list that could drift. Unreadable schema fails closed with a named error rather
    than falling back to a list (FIX-07).
    """
    try:
        schema = json.loads(ROUTE_GRAPH_SCHEMA.read_text(encoding="utf-8"))
        roles = schema["properties"]["nodes"]["items"]["properties"]["role"]["enum"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PageRoleSchemaUnavailable(
            f"cannot read the page-role enum from {ROUTE_GRAPH_SCHEMA}: {exc}") from exc
    return tuple(str(role) for role in roles)


@lru_cache(maxsize=None)
def page_structure_roles() -> tuple:
    """The roles references/page-structures.json gives their own section structure."""
    try:
        data = json.loads(PAGE_STRUCTURES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    roles = data.get("roles") if isinstance(data, dict) else None
    return tuple(str(role) for role in roles) if isinstance(roles, dict) else ()


def validate_page_role(role) -> str:
    """The schema spelling of `role`, or PageRoleUnknown quoting the rejected value.

    Separator normalisation is copy_forms.norm: ONE normaliser for both spelling boundaries
    (FIX-14), so "product_selection" and "product-selection" are the same slot here and the
    intake boundary names the same registry key.
    """
    if isinstance(role, str):
        wanted = copy_forms.slug(role)
        if wanted:
            for known in schema_page_roles():
                if copy_forms.slug(known) == wanted:
                    return known
    raise PageRoleUnknown(
        f"page role {role!r} is not one of the route-graph roles "
        f"{', '.join(schema_page_roles())}")


def role_form(role):
    """The registered copy form a role (in either spelling) is built from, or None for landing."""
    canonical = validate_page_role(role)
    return None if canonical == LANDING_ROLE else copy_forms.form_for_role(canonical)


def register_page_role(role) -> str:
    """Validate `role` and prove Skill 71 can build it: landing forms, a copy spec, a page
    structure, or a registered form. PageRoleUnregistered names a schema role with none.

    FIX-07 invariant: every role the route-graph schema permits is registerable and
    validatable here, and a role the schema does not permit raises PageRoleUnknown naming it.
    """
    canonical = validate_page_role(role)
    if canonical == LANDING_ROLE:
        for form in copy_forms.LANDING_FORMS:
            copy_forms.load_spec(form)
        return canonical
    if (canonical in page_structure_roles() or spec_for_role(canonical)
            or copy_forms.form_for_role(canonical)):
        return canonical
    raise PageRoleUnregistered(
        f"page role {canonical!r} is permitted by the route-graph schema but Skill 71 has no "
        "copy spec, page structure or registered form for it")


def registered_page_roles() -> tuple:
    """Every schema role Skill 71 can register, in schema order (the coverage assertion)."""
    out = []
    for role in schema_page_roles():
        try:
            out.append(register_page_role(role))
        except PageRoleUnregistered:
            continue
    return tuple(out)


def owns_wireframe_wording(spec) -> bool:
    """A page type whose spec carries its own wireframe wording (`wireframe.form_label`, the
    thank-you page). Ownership is a wireframe-rendering question asked at the point of use; it
    never decides whether a role spec exists (FIX-15)."""
    wireframe = spec.get("wireframe") if isinstance(spec.get("wireframe"), dict) else {}
    return bool(wireframe.get("form_label"))


def declared_roles(spec) -> tuple:
    """Every page role the spec itself declares (`page_role`, or the plural `page_roles`)."""
    roles = []
    if spec.get("page_role"):
        roles.append(str(spec["page_role"]))
    roles.extend(str(role) for role in (spec.get("page_roles") or ()))
    return tuple(dict.fromkeys(roles))


def _registered_version(spec, path) -> str | None:
    """The key a discovered role spec is registered under. Never its position in the tree:
    its declared `copy_version`, else the form key copy_forms.SPEC_FILES gives its file
    (checkout declares no copy_version: its page version is the registry key "checkout"),
    else the role it declares."""
    if spec.get("copy_version"):
        return str(spec["copy_version"])
    rel = path.relative_to(SPEC_DIR).as_posix()
    for form, target in copy_forms.SPEC_FILES.items():
        if Path(target).as_posix() == rel:
            return str(form)
    roles = declared_roles(spec)
    return roles[0] if roles else None


def role_spec_paths() -> dict:
    """{registered version: path} for every role spec at any depth under references/copy-specs/.

    FIX-15: recursive, and discovery is not filtered by `wireframe.form_label` — that predicate
    belongs at the point of use, not in the registry."""
    out = {}
    for path in sorted(SPEC_DIR.rglob("*.json")):
        try:
            spec = _read(str(path))
        except (OSError, ValueError):
            continue
        if not isinstance(spec, dict) or not declared_roles(spec):
            continue
        version = _registered_version(spec, path)
        if version:
            out[version] = path
    return out


def role_specs() -> dict:
    """{registered version: spec} for every role spec at any depth under references/copy-specs/."""
    return {version: _read(str(path)) for version, path in role_spec_paths().items()}


def _spec_on_disk(role):
    """The path of a role spec file on disk for `role`, independent of discovery."""
    if not isinstance(role, str) or not role:
        return None
    for path in sorted(SPEC_DIR.rglob("*.json")):
        try:
            spec = _read(str(path))
        except (OSError, ValueError):
            continue
        if isinstance(spec, dict) and role in declared_roles(spec):
            return path
    return None


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
    path = role_spec_paths().get(str(version))
    if path is None:
        return ""
    return f"references/copy-specs/{path.relative_to(SPEC_DIR).as_posix()}"


def spec_for_role(role):
    """The role's own spec. None only for a role with no spec file at all (landing).

    FIX-15: a role that has a spec on disk but is missing from discovery raises
    RoleSpecNotDiscovered naming the role and the path, never a silent None."""
    for spec in role_specs().values():
        if role in declared_roles(spec):
            return spec
    path = _spec_on_disk(role)
    if path is not None:
        raise RoleSpecNotDiscovered(
            f"page role {role!r} has a spec at {path} but page_role.role_specs() did not "
            "discover it; every references/copy-specs/**/*.json role spec must be in the registry")
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
            # FIX-07: a declared role is validated against the route-graph schema here, the
            # read path every stage and the gate share; an out-of-schema token never floats.
            return validate_page_role(value)
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


# The section that exists exactly when the funnel has an order bump (loop decision, 2026-11-02):
# a request that says `order_bump: false` has no such section and refuses a stray one; a request
# that says true, or says nothing, keeps the spec's full sequence and still requires it.
BUMP_SECTION = {"checkout": "3"}


def allowed_sequences(spec, request=None) -> list:
    """Every canonical section sequence a spec accepts: its own, plus each optional-children
    expansion (5 -> 5A,5B,5C), minus the order bump section when the request says
    `order_bump: false`. ONE resolver, read by both the request builder and the
    executor, so neither accepts a manuscript the other refuses."""
    base = list(spec["sequence"])
    out = [base]
    for parent, child in ((spec.get("containment") or {}).get("child_sections") or {}).items():
        if parent in base and child.get("ids"):
            i = base.index(parent)
            out.append(base[:i] + list(child["ids"]) + base[i + 1:])
    bump = BUMP_SECTION.get(spec.get("page_role"))
    if bump and isinstance(request, dict) and request.get("order_bump") is False:
        out = [[i for i in seq if i != bump] for seq in out]
    return out


def child_names(spec) -> dict:
    """{child section id: name} for every optional child section (5A, 5B, 5C), from the spec's
    containment block: a child has no entry of its own in `sections`."""
    return {cid: name for block in (((spec.get("containment") or {}).get("child_sections")) or {}).values()
            for cid, name in (block.get("names") or {}).items()}


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
