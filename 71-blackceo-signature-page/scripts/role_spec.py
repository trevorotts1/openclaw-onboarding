#!/usr/bin/env python3
"""role_spec.py - per-page-role section structure for Skill 71's image pipeline.

The 12- and 15-section landing structures live in references/copy-specs/
{standard,long-form}-v6.json. Every other page role (checkout today) has its
own, shorter canonical sequence in references/copy-specs/roles/<role>.json.
A run whose page_role has such a file is checked, built and drawn against it;
a role with no file (landing) keeps the copy_version spec unchanged.

One loader, used by stage_executor.py, build_production_request.py,
composition.py and wireframe_spec.py, so the structure is never duplicated.
"""
from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
ROLES_DIR = SKILL_ROOT / "references" / "copy-specs" / "roles"
FORMS = ("standard", "long-form")


@lru_cache(maxsize=None)
def load(role):
    """The role's spec dict, or None when the role has no spec file (landing)."""
    if not isinstance(role, str) or not re.fullmatch(r"[a-z0-9_]+", role):
        return None
    path = ROLES_DIR / f"{role}.json"
    if not path.is_file():
        return None
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("page_role") != role or spec.get("form") not in FORMS:
        raise ValueError(f"{path.name}: page_role must be {role!r} and form one of {FORMS}")
    return spec


def role_of(run_dir, request):
    """The request's page_role, else metadata.page_role, else the run's declared role."""
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    role = request.get("page_role") or metadata.get("page_role")
    if role:
        return role
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    try:
        import design_board
    finally:
        sys.path.pop(0)
    return design_board.declared_role(Path(run_dir))


def for_request(run_dir, request):
    """The role spec governing this request, or None for a landing run."""
    return load(role_of(run_dir, request))


def section(spec, section_id):
    """The spec's entry for one canonical section id ({} when absent)."""
    return next((s for s in spec["sections"] if s["id"] == str(section_id)), {})
