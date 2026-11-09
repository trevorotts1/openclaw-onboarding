"""Buildable-template manifest and fail-closed build_graph validation."""
from __future__ import annotations

import json
import os
from typing import Any

MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "buildable-templates.json",
)


def load_manifest(path: str | None = None) -> dict[str, dict]:
    """Load qualified buildable-template records; tolerate missing manifests."""
    try:
        with open(path or MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        templates = data.get("templates", [])
        if not isinstance(templates, list):
            return {}
        result = {}
        for item in templates:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            template_path = item.get("path")
            kind = item.get("kind")
            if isinstance(key, str) and isinstance(template_path, str) and isinstance(kind, str):
                result[key] = {"path": template_path, "kind": kind}
        return result
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError, TypeError):
        return {}


def is_buildable(
    tmpl: dict,
    manifest: dict[str, dict] | None = None,
) -> bool:
    """Check whether template's qualified key appears in buildable manifest."""
    if not isinstance(tmpl, dict):
        return False
    group = tmpl.get("group")
    tid = tmpl.get("id")
    if not isinstance(group, str) or not group or not isinstance(tid, str) or not tid:
        return False
    return f"{group}/{tid}" in (load_manifest() if manifest is None else manifest)


def annotate(
    templates: list[dict],
    manifest: dict[str, dict] | None = None,
) -> list[dict]:
    """Annotate template records in place and return original list."""
    resolved = load_manifest() if manifest is None else manifest
    for template in templates:
        template["buildable"] = is_buildable(template, resolved)
    return templates


def graph_for(tmpl: dict) -> list | None:
    """Read a non-empty build_graph from template's source file."""
    source_path = tmpl.get("sourcePath") if isinstance(tmpl, dict) else None
    if not isinstance(source_path, str) or not source_path:
        return None
    try:
        with open(source_path, encoding="utf-8") as f:
            document = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(document, dict):
        return None
    graph = document.get("build_graph")
    return graph if isinstance(graph, list) and graph else None


def describe(tmpl: dict) -> dict[str, Any]:
    """Apply fail-closed Part-E contract for graph-backed build plans."""
    if not tmpl.get("buildable"):
        return {"buildable": False, "build_graph": None}

    graph = graph_for(tmpl)
    if graph is None:
        raise ValueError(
            f"buildable template without build_graph: {tmpl.get('sourcePath')}"
        )
    return {"buildable": True, "build_graph": graph}
