#!/usr/bin/env python3
"""Offline n8n workflow transformer for Podbean client credentials.

This program reads and writes local workflow JSON only. It has no networking
code and never accepts a secret value as a command-line argument.

--check placeholder semantics: a REPLACE_WITH_...CREDENTIAL... placeholder is
the sanctioned sanitized form this transformer emits for credential IDs (see
CREDENTIAL_ID_PLACEHOLDER) and the form shipped in committed workflow exports.
--check therefore treats a placeholder value as CLEAN (exit 0) and only flags
plaintext secret literals (exit 1). Rejecting placeholders would condemn the
transformer's own output and the committed broker export, so clean-is-correct.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


CREDENTIAL_ID_PLACEHOLDER = "REPLACE_WITH_PODBEAN_CREDENTIAL_ID"
ENV_BY_KEY = {
    "client_id": "PODBEAN_CLIENT_ID",
    "client_secret": "PODBEAN_CLIENT_SECRET",
}

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
    (?P<literal>(?P<value_quote>[\"'`])(?P<value>.*?)(?P=value_quote))
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
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


def secret_key(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    normalized = raw.replace("_", "").casefold()
    if normalized == "clientid":
        return "client_id"
    if normalized == "clientsecret":
        return "client_secret"
    return None


def is_plain_literal(value: object) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith("={{") and stripped.endswith("}}"):
        return False
    if "$env." in stripped.casefold():
        return False
    if PLACEHOLDER_RE.fullmatch(stripped):
        return False
    return True


def env_expression(kind: str) -> str:
    return f"={{{{ $env.{ENV_BY_KEY[kind]} }}}}"


def node_kind(node_type: object) -> str | None:
    if not isinstance(node_type, str):
        return None
    suffix = node_type.rsplit(".", 1)[-1].casefold()
    if suffix == "code":
        return "code"
    if suffix == "set":
        return "set"
    if suffix == "httprequest":
        return "http_request"
    return None


def report_change(changes: list[dict[str, str]], node: str, key: str, location: str, action: str) -> None:
    changes.append({"node": node, "key": key, "location": location, "action": action})


def rewrite_structured_to_env(
    value: Any,
    *,
    node_name: str,
    path: str,
    changes: list[dict[str, str]],
    removed_literals: list[str],
    env_vars: set[str],
) -> None:
    if isinstance(value, dict):
        pair_kind = secret_key(value.get("name"))
        if pair_kind and is_plain_literal(value.get("value")):
            removed_literals.append(value["value"])
            value["value"] = env_expression(pair_kind)
            env_vars.add(ENV_BY_KEY[pair_kind])
            report_change(changes, node_name, pair_kind, f"{path}.value", f"<redacted> -> $env.{ENV_BY_KEY[pair_kind]}")

        for raw_key in list(value):
            child = value[raw_key]
            kind = secret_key(raw_key)
            if kind and is_plain_literal(child):
                removed_literals.append(child)
                value[raw_key] = env_expression(kind)
                env_vars.add(ENV_BY_KEY[kind])
                report_change(changes, node_name, kind, f"{path}.{raw_key}", f"<redacted> -> $env.{ENV_BY_KEY[kind]}")
                continue
            rewrite_structured_to_env(
                child,
                node_name=node_name,
                path=f"{path}.{raw_key}",
                changes=changes,
                removed_literals=removed_literals,
                env_vars=env_vars,
            )
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            rewrite_structured_to_env(
                child,
                node_name=node_name,
                path=f"{path}[{index}]",
                changes=changes,
                removed_literals=removed_literals,
                env_vars=env_vars,
            )


def rewrite_code_text(
    text: str,
    *,
    node_name: str,
    location: str,
    changes: list[dict[str, str]],
    removed_literals: list[str],
    env_vars: set[str],
) -> str:
    pieces: list[str] = []
    cursor = 0
    for match in KEY_ASSIGNMENT_RE.finditer(text):
        literal = match.group("value")
        if not is_plain_literal(literal):
            continue
        raw_key = (
            match.group("bracket_key")
            or match.group("quoted_key")
            or match.group("bare_key")
        )
        kind = secret_key(raw_key)
        if kind is None:
            continue
        pieces.append(text[cursor : match.start("literal")])
        pieces.append(f"$env.{ENV_BY_KEY[kind]}")
        cursor = match.end("literal")
        removed_literals.append(literal)
        env_vars.add(ENV_BY_KEY[kind])
        report_change(changes, node_name, kind, location, f"<redacted> -> $env.{ENV_BY_KEY[kind]}")

    if not pieces:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces)


def rewrite_code_strings(
    value: Any,
    *,
    node_name: str,
    path: str,
    changes: list[dict[str, str]],
    removed_literals: list[str],
    env_vars: set[str],
) -> Any:
    if isinstance(value, dict):
        for raw_key in list(value):
            value[raw_key] = rewrite_code_strings(
                value[raw_key],
                node_name=node_name,
                path=f"{path}.{raw_key}",
                changes=changes,
                removed_literals=removed_literals,
                env_vars=env_vars,
            )
        return value
    if isinstance(value, list):
        for index, child in enumerate(value):
            value[index] = rewrite_code_strings(
                child,
                node_name=node_name,
                path=f"{path}[{index}]",
                changes=changes,
                removed_literals=removed_literals,
                env_vars=env_vars,
            )
        return value
    if isinstance(value, str):
        return rewrite_code_text(
            value,
            node_name=node_name,
            location=path,
            changes=changes,
            removed_literals=removed_literals,
            env_vars=env_vars,
        )
    return value


DROP = object()


def remove_http_literals(
    value: Any,
    *,
    node_name: str,
    path: str,
    changes: list[dict[str, str]],
    removed_literals: list[str],
) -> Any:
    if isinstance(value, dict):
        pair_kind = secret_key(value.get("name"))
        if pair_kind and is_plain_literal(value.get("value")):
            removed_literals.append(value["value"])
            report_change(changes, node_name, pair_kind, f"{path}.value", "<redacted> -> removed (HTTP Basic credential)")
            return DROP

        for raw_key in list(value):
            child = value[raw_key]
            kind = secret_key(raw_key)
            if kind and is_plain_literal(child):
                removed_literals.append(child)
                del value[raw_key]
                report_change(changes, node_name, kind, f"{path}.{raw_key}", "<redacted> -> removed (HTTP Basic credential)")
                continue
            transformed = remove_http_literals(
                child,
                node_name=node_name,
                path=f"{path}.{raw_key}",
                changes=changes,
                removed_literals=removed_literals,
            )
            if transformed is DROP:
                del value[raw_key]
            else:
                value[raw_key] = transformed
        return value

    if isinstance(value, list):
        rewritten: list[Any] = []
        for index, child in enumerate(value):
            transformed = remove_http_literals(
                child,
                node_name=node_name,
                path=f"{path}[{index}]",
                changes=changes,
                removed_literals=removed_literals,
            )
            if transformed is not DROP:
                rewritten.append(transformed)
        return rewritten

    return value


def set_if_changed(
    mapping: dict[str, Any],
    key: str,
    value: Any,
    *,
    node_name: str,
    location: str,
    changes: list[dict[str, str]],
    action: str,
) -> None:
    if mapping.get(key) == value:
        return
    mapping[key] = value
    report_change(changes, node_name, key, location, action)


def redact_name(name: str, removed_literals: list[str]) -> str:
    result = name
    for literal in sorted(set(removed_literals), key=len, reverse=True):
        if literal:
            result = result.replace(literal, "<redacted>")
    return result


def transform_workflow(workflow: dict[str, Any], credential_name: str) -> tuple[list[dict[str, str]], set[str], list[str]]:
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("workflow JSON must contain a nodes array")

    changes: list[dict[str, str]] = []
    env_vars: set[str] = set()
    removed_literals: list[str] = []

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        kind = node_kind(node.get("type"))
        if kind is None:
            continue
        raw_name = node.get("name")
        node_name = raw_name if isinstance(raw_name, str) and raw_name else f"<unnamed node {index}>"
        parameters = node.get("parameters")
        if not isinstance(parameters, dict):
            continue

        before = len(changes)
        if kind in {"code", "set"}:
            rewrite_structured_to_env(
                parameters,
                node_name=node_name,
                path="parameters",
                changes=changes,
                removed_literals=removed_literals,
                env_vars=env_vars,
            )
            if kind == "code":
                rewrite_code_strings(
                    parameters,
                    node_name=node_name,
                    path="parameters",
                    changes=changes,
                    removed_literals=removed_literals,
                    env_vars=env_vars,
                )
        elif kind == "http_request":
            node["parameters"] = remove_http_literals(
                parameters,
                node_name=node_name,
                path="parameters",
                changes=changes,
                removed_literals=removed_literals,
            )
            if len(changes) > before:
                parameters = node["parameters"]
                set_if_changed(
                    parameters,
                    "authentication",
                    "predefinedCredentialType",
                    node_name=node_name,
                    location="parameters.authentication",
                    changes=changes,
                    action="set for named credential",
                )
                set_if_changed(
                    parameters,
                    "nodeCredentialType",
                    "httpBasicAuth",
                    node_name=node_name,
                    location="parameters.nodeCredentialType",
                    changes=changes,
                    action="set for named credential",
                )
                credentials = node.setdefault("credentials", {})
                if not isinstance(credentials, dict):
                    credentials = {}
                    node["credentials"] = credentials
                credential_ref = {
                    "id": CREDENTIAL_ID_PLACEHOLDER,
                    "name": credential_name,
                }
                set_if_changed(
                    credentials,
                    "httpBasicAuth",
                    credential_ref,
                    node_name=node_name,
                    location="credentials.httpBasicAuth",
                    changes=changes,
                    action=f"set placeholder {CREDENTIAL_ID_PLACEHOLDER!r} for named credential",
                )

    for change in changes:
        change["node"] = redact_name(change["node"], removed_literals)
    return changes, env_vars, removed_literals


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


# -- plaintext secret patterns for --check scan (exit-0-clean / exit-1-dirty) ------

# patterns that look like non-trivial secrets (long random-looking strings, API keys, tokens)
SECRET_PATTERNS = [
    re.compile(r"[A-Za-z0-9]{32,}"),                # 32+ char alphanumeric (tokens, keys)
    re.compile(r"[A-Za-z0-9+/=]{40,}"),              # base64-ish
    re.compile(r"(?:sk|pk|api[_-]?key|secret|token|password|passwd)[=:]\s*\S+", re.IGNORECASE),
]


def _matches_secret_pattern(value: str) -> bool:
    """True if `value` looks like a plaintext secret.

    env references (={{ $env.X }} / $env.X) and REPLACE_WITH_...CREDENTIAL...
    placeholders are the sanctioned sanitized forms this transformer emits and
    that committed exports ship, so they are NOT secrets and return False.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith("={{") and stripped.endswith("}}"):
        return False
    if "$env." in stripped.casefold():
        return False
    if PLACEHOLDER_RE.fullmatch(stripped):
        return False
    for pat in SECRET_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def _collect_secrets(value: Any, path: str, findings: list[str]) -> None:
    """Recurse through the workflow tree and collect plaintext-secret locations."""
    if isinstance(value, dict):
        for raw_key, child in value.items():
            child_path = f"{path}.{raw_key}"
            if isinstance(child, str) and secret_key(raw_key) and _matches_secret_pattern(child):
                findings.append(f"{child_path} = <redacted> (plaintext {secret_key(raw_key)})")
            else:
                _collect_secrets(child, child_path, findings)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            _collect_secrets(child, f"{path}[{idx}]", findings)
    elif isinstance(value, str):
        # scan code/JS strings embedded in node parameters
        for match in KEY_ASSIGNMENT_RE.finditer(value):
            literal = match.group("value")
            raw_key = (
                match.group("bracket_key")
                or match.group("quoted_key")
                or match.group("bare_key")
            )
            kind = secret_key(raw_key)
            if kind and is_plain_literal(literal):
                findings.append(f"{path} = <redacted> (plaintext {kind} in code)")


def check_workflow(workflow_text: str) -> tuple[bool, list[str]]:
    """Read-only scan for plaintext secrets (--check). Returns (clean, findings)."""
    try:
        data = json.loads(workflow_text)
    except (ValueError, TypeError) as exc:
        return False, [f"not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return False, ["workflow JSON must be an object"]

    findings: list[str] = []
    nodes = data.get("nodes")
    if isinstance(nodes, list):
        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            raw_name = node.get("name")
            node_name = raw_name if isinstance(raw_name, str) and raw_name else f"<node-{idx}>"
            _collect_secrets(node, node_name, findings)

    return not findings, findings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove plaintext Podbean client credentials from an offline n8n workflow export.",
    )
    parser.add_argument("workflow", type=Path, help="local n8n workflow JSON export")
    parser.add_argument("credential_name", nargs="?", help="target n8n credential name")
    parser.add_argument("--credential-name", dest="credential_name_option", help="target n8n credential name")
    parser.add_argument("--output", type=Path, help="output path (default: rewrite the input atomically)")
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "read-only scan for plaintext secrets "
            "(exit 0=clean, 1=dirty). REPLACE_WITH_...CREDENTIAL... "
            "placeholders are the sanctioned sanitized form and exit 0 (clean)."
        ),
    )
    args = parser.parse_args(argv)

    if args.check:
        # --check does not require a credential name
        args.resolved_credential_name = args.credential_name_option or args.credential_name or ""
        return args

    if args.credential_name and args.credential_name_option:
        parser.error("provide the credential name either positionally or with --credential-name, not both")
    args.resolved_credential_name = args.credential_name_option or args.credential_name
    if not args.resolved_credential_name or not args.resolved_credential_name.strip():
        parser.error("a non-empty target credential name is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    source = args.workflow.resolve()

    # --- --check: read-only plaintext-secret scan --------------------------------
    if args.check:
        try:
            text = source.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"ERROR: workflow file not found: {source}", file=sys.stderr)
            return 2
        except (OSError, UnicodeError, json.JSONDecodeError):
            print(f"ERROR: workflow file is not readable valid JSON: {source}", file=sys.stderr)
            return 2

        clean, findings = check_workflow(text)
        if clean:
            print(f"CLEAN: no plaintext secrets found in {source.name}")
            return 0
        else:
            for f in findings:
                print(f"DIRTY: {f}", file=sys.stderr)
            print(f"DIRTY: {len(findings)} plaintext secret(s) found in {source.name}", file=sys.stderr)
            return 1

    # --- transform (vault) ------------------------------------------------------
    destination = (args.output or args.workflow).resolve()

    try:
        workflow = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: workflow file not found: {source}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, json.JSONDecodeError):
        print(f"ERROR: workflow file is not readable valid JSON: {source}", file=sys.stderr)
        return 2

    if not isinstance(workflow, dict):
        print("ERROR: workflow JSON root must be an object", file=sys.stderr)
        return 2

    try:
        changes, env_vars, _removed_literals = transform_workflow(
            workflow, args.resolved_credential_name.strip()
        )
        rendered = json.dumps(workflow, indent=2, ensure_ascii=False) + "\n"
        atomic_write(destination, rendered)
    except (OSError, ValueError):
        print("ERROR: workflow transformation or output write failed", file=sys.stderr)
        return 2

    print(f"Vaulting report: {len(changes)} change(s) written to {destination}")
    if changes:
        for change in changes:
            print(
                f"- node {change['node']!r}: {change['location']} "
                f"[{change['key']}] -- {change['action']}"
            )
    else:
        print("- no plaintext client credential literals found in supported nodes")

    if env_vars:
        print(f"Required n8n deployment env vars: {', '.join(sorted(env_vars))}")
    else:
        print("Required n8n deployment env vars: none")
    print(
        "Credential placeholder: "
        f"{CREDENTIAL_ID_PLACEHOLDER} -> {args.resolved_credential_name.strip()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
