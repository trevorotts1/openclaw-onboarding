#!/usr/bin/env bash
# qc-assert-no-n8n-plaintext-secrets.sh — GK-03 n8n workflow secret guard.
#
# STATIC QC INVARIANT: discovers every *.workflow.json under the repository and
# fails when a node parameter or code string assigns a plaintext string literal
# to client_id, client_secret, clientId, or clientSecret (case-insensitive).
# n8n expressions, $env references, and obvious credential-ID placeholders are
# references rather than secret literals and are allowed.
#
# Security: diagnostics identify only the file, node, and key. The rejected
# literal is never printed.
#
# Exit codes:
#   0 — every discovered workflow is clean
#   1 — one or more plaintext assignments (or invalid workflow JSON files) found
#   2 — usage/environment error
#
# Usage:
#   bash scripts/qc-assert-no-n8n-plaintext-secrets.sh
#   bash scripts/qc-assert-no-n8n-plaintext-secrets.sh --repo-root /path/to/repo

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root)
      [ $# -ge 2 ] || { echo "missing value for --repo-root" >&2; exit 2; }
      REPO_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '1,25p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

[ -d "$REPO_ROOT" ] || { echo "repository root not found: $REPO_ROOT" >&2; exit 2; }

python3 - "$REPO_ROOT" <<'PY'
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterator


REPO_ROOT = Path(sys.argv[1]).resolve()
SKIP_PARTS = {".git", "node_modules", ".venv", "venv"}

KEY_ASSIGNMENT_RE = re.compile(
    r"""
    (?:
        \[\s*(?P<bracket_quote>[\"'])(?P<bracket_key>client_?id|client_?secret)
            (?P=bracket_quote)\s*\]
      |
        (?<![\w$])
        (?:
            (?P<key_quote>[\"'])(?P<quoted_key>client_?id|client_?secret)(?P=key_quote)
          |
            (?P<bare_key>client_?id|client_?secret)
        )
        (?![\w$])
    )
    \s*(?::|=(?!=|>))\s*
    (?P<literal>
        (?P<value_quote>[\"'`])
        (?P<value>(?:\\.|(?!(?P=value_quote)).)*)
        (?P=value_quote)
    )
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

QUERY_ASSIGNMENT_RE = re.compile(
    r"[?&](?P<key>client_?id|client_?secret)=(?P<value>[^&#\s\"'`]+)",
    re.IGNORECASE,
)

PLACEHOLDER_RE = re.compile(
    r"^(?:"
    r"REPLACE_WITH_[A-Z0-9_]*CREDENTIAL[A-Z0-9_]*"
    r"|[A-Z0-9_]*CREDENTIAL(?:_ID)?_PLACEHOLDER"
    r"|PLACEHOLDER_[A-Z0-9_]*CREDENTIAL(?:_ID)?"
    r"|<[^>]*CREDENTIAL(?:[_ -]?ID)?[^>]*>"
    r")$",
    re.IGNORECASE,
)

ENV_REFERENCE_RE = re.compile(r"^\$env\.[A-Z_][A-Z0-9_]*$", re.IGNORECASE)


def secret_key(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    normalized = raw.replace("_", "").casefold()
    if normalized == "clientid":
        return "client_id"
    if normalized == "clientsecret":
        return "client_secret"
    return None


def is_plain_literal(value: object, *, allow_env_reference: bool = True) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith("={{") and stripped.endswith("}}"):
        return False
    if allow_env_reference and ENV_REFERENCE_RE.fullmatch(stripped):
        return False
    if PLACEHOLDER_RE.fullmatch(stripped):
        return False
    return True


def code_assignments(text: str) -> Iterator[tuple[str, str]]:
    occupied: list[tuple[int, int]] = []
    for match in KEY_ASSIGNMENT_RE.finditer(text):
        key = (
            match.group("bracket_key")
            or match.group("quoted_key")
            or match.group("bare_key")
        )
        value = match.group("value")
        # A quoted "$env.NAME" inside Code is still a string literal, not an
        # evaluated environment reference. Only unquoted references are safe.
        if is_plain_literal(value, allow_env_reference=False):
            occupied.append(match.span())
            yield secret_key(key) or key, value

    for match in QUERY_ASSIGNMENT_RE.finditer(text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        value = match.group("value")
        # A query-string value containing $env text is still literal unless the
        # surrounding n8n parameter is itself an expression.
        if is_plain_literal(value, allow_env_reference=False):
            yield secret_key(match.group("key")) or match.group("key"), value


def parameter_hits(value: object, path: str = "parameters") -> Iterator[tuple[str, str, str]]:
    if isinstance(value, dict):
        pair_kind = secret_key(value.get("name"))
        if pair_kind and is_plain_literal(value.get("value")):
            yield pair_kind, f"{path}.value", value["value"]

        for raw_key, child in value.items():
            kind = secret_key(raw_key)
            if kind and is_plain_literal(child):
                yield kind, f"{path}.{raw_key}", child
            yield from parameter_hits(child, f"{path}.{raw_key}")
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from parameter_hits(child, f"{path}[{index}]")
        return

    if isinstance(value, str):
        for kind, literal in code_assignments(value):
            yield kind, path, literal


def redact_node_name(raw_name: object, literals: list[str]) -> str:
    name = raw_name if isinstance(raw_name, str) and raw_name else "<unnamed>"
    for literal in sorted(set(literals), key=len, reverse=True):
        if literal:
            name = name.replace(literal, "<redacted>")
    return name


workflows = sorted(
    path for path in REPO_ROOT.rglob("*.workflow.json")
    if not any(part in SKIP_PARTS for part in path.relative_to(REPO_ROOT).parts)
)

if not workflows:
    print(f"CANNOT RESOLVE — no *.workflow.json files found under: {REPO_ROOT}", file=sys.stderr)
    raise SystemExit(2)

violations: list[tuple[str, str, str, str]] = []
invalid: list[str] = []

for workflow_path in workflows:
    relative = str(workflow_path.relative_to(REPO_ROOT))
    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        invalid.append(relative)
        continue

    if not isinstance(workflow, dict):
        invalid.append(relative)
        continue
    nodes = workflow.get("nodes", [])
    if not isinstance(nodes, list):
        invalid.append(relative)
        continue

    for node in nodes:
        if not isinstance(node, dict):
            continue
        hits = list(parameter_hits(node.get("parameters", {})))
        if not hits:
            continue
        literals = [literal for _key, _path, literal in hits]
        node_name = redact_node_name(node.get("name"), literals)
        for key, _location, literal in hits:
            violations.append((relative, node_name, key, literal))

if invalid:
    for relative in invalid:
        print(f"[qc-n8n-secrets] FATAL {relative}: invalid workflow JSON", file=sys.stderr)

if violations:
    literals_by_file: dict[str, list[str]] = {}
    for relative, _node_name, _key, literal in violations:
        literals_by_file.setdefault(relative, []).append(literal)

    for relative, node_name, key, _literal in violations:
        redacted_relative = redact_node_name(relative, literals_by_file[relative])
        redacted_node_name = redact_node_name(node_name, literals_by_file[relative])
        print(
            f"[qc-n8n-secrets] FATAL {redacted_relative}: "
            f"node {redacted_node_name!r} has plaintext {key}",
            file=sys.stderr,
        )

if invalid or violations:
    print(
        f"[qc-n8n-secrets] INVARIANT VIOLATED — "
        f"{len(violations)} plaintext assignment(s), {len(invalid)} invalid workflow file(s)",
        file=sys.stderr,
    )
    raise SystemExit(1)

print(
    f"[qc-n8n-secrets] PASS — {len(workflows)} workflow file(s) checked; "
    "no plaintext client credential assignments found"
)
PY
