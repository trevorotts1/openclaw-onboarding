#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: n8n workflow schema validation (U041)
# -----------------------------------------------------------------------------
# F41: config/n8n/podbean-publish.workflow.json was committed with no version
# marker and no schema validation, so a corrupted or incompatible workflow could
# be imported into n8n with no pre-flight check. This validator is that pre-flight
# check: it parses the JSON, asserts the required n8n structure (nodes +
# connections), asserts the explicit meta.version marker (U041), and asserts an
# n8n schema-version compatibility floor.
#
# The core is a PURE function (validate_workflow) so the QC gate and the unit
# tests drive it without touching the filesystem; the CLI wraps it for the gate.
#
# Usage:
#   python3 validate_n8n_workflow.py path/to/workflow.json
#   python3 validate_n8n_workflow.py path/to/workflow.json --min-n8n 1.0
#
# Exit codes: 0 = valid, 1 = invalid (reason on stderr), 2 = unreadable file.
#
# QC GATE WIRING (follow-up after U031 merges): qc-podcast.sh (created by U031,
# not yet on main) should add one assert that calls this validator on the
# workflow JSON, e.g.:
#   assert "n8n workflow JSON valid + versioned" \
#     "python3 \"$SKILL_DIR/scripts/validate_n8n_workflow.py\" \"$SKILL_DIR/config/n8n/podbean-publish.workflow.json\""
# =============================================================================
"""n8n workflow JSON schema + version validation (U041 / F41)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

# The n8n schema-version floor this workflow is known to import under. A
# workflow whose meta.minN8nSchemaVersion is above the target n8n's version is
# incompatible; the validator refuses it rather than letting a too-new workflow
# reach an older n8n.
DEFAULT_MIN_N8N = "1.0"


@dataclass
class ValidationResult:
    """The verdict + the specific problems found (empty list == valid)."""
    ok: bool
    problems: list[str] = field(default_factory=list)
    version: str | None = None
    node_count: int = 0
    connection_count: int = 0


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse a dotted version ('1.0', '1.2.3') into a comparable int tuple.
    Non-numeric / missing segments degrade to 0 so comparison never throws."""
    parts = []
    for seg in str(v).split("."):
        digits = "".join(ch for ch in seg if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def validate_workflow(
    workflow_text: str,
    *,
    min_n8n: str = DEFAULT_MIN_N8N,
) -> ValidationResult:
    """Validate an n8n workflow JSON string.

    Checks, in order (all problems are collected, not just the first):
      1. parses as JSON (an object, not a list/scalar)
      2. `nodes` is present and a non-empty list
      3. `connections` is present and an object
      4. `meta.version` is present and a non-empty string (the U041 marker)
      5. the workflow's declared minN8nSchemaVersion does not exceed the target
         n8n version (compatibility floor)

    Never throws on content; a garbage string yields a parse problem.
    """
    problems: list[str] = []

    # 1. parse
    try:
        data = json.loads(workflow_text)
    except (ValueError, TypeError) as exc:
        return ValidationResult(False, [f"not valid JSON: {exc}"])
    if not isinstance(data, dict):
        return ValidationResult(False, ["workflow JSON must be an object"])

    # 2. nodes
    nodes = data.get("nodes")
    node_count = 0
    if not isinstance(nodes, list):
        problems.append("missing or non-list 'nodes' field")
    elif not nodes:
        problems.append("'nodes' is empty — a workflow must define at least one node")
    else:
        node_count = len(nodes)

    # 3. connections
    connections = data.get("connections")
    connection_count = 0
    if not isinstance(connections, dict):
        problems.append("missing or non-object 'connections' field")
    else:
        connection_count = len(connections)

    # 4. version marker (U041)
    meta = data.get("meta")
    version = None
    if not isinstance(meta, dict):
        problems.append("missing 'meta' object — the workflow must carry a version marker (U041)")
    else:
        v = meta.get("version")
        if not isinstance(v, str) or not v.strip():
            problems.append("missing or empty 'meta.version' field (U041)")
        else:
            version = v.strip()

    # 5. n8n schema-version compatibility floor
    if isinstance(meta, dict):
        declared = meta.get("minN8nSchemaVersion")
        if isinstance(declared, str) and declared.strip():
            if _version_tuple(declared) > _version_tuple(min_n8n):
                problems.append(
                    f"workflow requires n8n schema >= {declared}, but target is {min_n8n} "
                    f"(incompatible — upgrade the target n8n or lower the workflow floor)"
                )

    return ValidationResult(
        ok=not problems,
        problems=problems,
        version=version,
        node_count=node_count,
        connection_count=connection_count,
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Validate an n8n workflow JSON (U041).")
    p.add_argument("workflow", help="path to the workflow JSON file")
    p.add_argument("--min-n8n", default=DEFAULT_MIN_N8N,
                   help=f"target n8n schema version floor (default {DEFAULT_MIN_N8N})")
    args = p.parse_args(argv)

    try:
        with open(args.workflow, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"error: cannot read workflow file: {exc}", file=sys.stderr)
        return 2

    result = validate_workflow(text, min_n8n=args.min_n8n)
    if result.ok:
        print(f"VALID: version={result.version} nodes={result.node_count} "
              f"connections={result.connection_count}")
        return 0
    for problem in result.problems:
        print(f"INVALID: {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
