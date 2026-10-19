#!/usr/bin/env python3
"""GHL-110 operation-routing matrix gate (stdlib only).

Fails when:

* a retired community-MCP rail token appears in a file the manifest has not
  classified, or on a line inside a caller file that is neither a declared
  caller line nor an exempt retirement line;
* a declared caller line is missing, or does not contain the evidence pattern;
* a caller has no replacement, or a replacement operation id is not in the
  frozen registry, or the recorded method/path/version disagrees with the row;
* a replacement points at a staging-only row (``documented_level == "S"`` or
  version ``v4``) -- staging is never presented as production;
* the alias fixture maps a community tool to a staging row without an explicit
  fallback.

Run: python3 -I evidence/W11/test_operation_routing_matrix.py
Exit 0 = matrix complete, exit 1 = gap.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
MANIFEST_PATH = ROOT / "evidence" / "W11" / "operation-routing-manifest.json"
ENGINE = ROOT / "44-convert-and-flow-operator" / "tools" / "engine"

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}
SKIP_PREFIX = ("evidence/W11/",)


def fail(message: str) -> None:
    raise AssertionError(message)


def load_manifest() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for key in ("retired_rail_tokens", "callers", "files"):
        if key not in manifest:
            fail(f"manifest missing {key}")
    return manifest


def load_registry():
    sys.path.insert(0, str(ENGINE))
    from cli_anything.gohighlevel.public.operations import OPERATIONS  # type: ignore

    return OPERATIONS


def walk_text_files(manifest: dict):
    patterns = [re.compile(p, re.MULTILINE) for p in manifest["retired_rail_tokens"]]
    scanned: dict[str, list[tuple[int, str]]] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if rel.startswith(SKIP_PREFIX):
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        text = raw.decode("utf-8", "ignore")
        lines = text.splitlines()
        hits: list[tuple[int, str]] = []
        for lineno, line in enumerate(lines, start=1):
            if any(pattern.search(line) for pattern in patterns):
                hits.append((lineno, line))
        if hits:
            scanned[rel] = hits
    return scanned


def check_files(manifest: dict, scanned: dict[str, list[tuple[int, str]]]) -> int:
    declared = manifest["files"]
    errors = 0
    for rel in sorted(scanned):
        if rel not in declared:
            print(f"FAIL unclassified retired-rail reference: {rel}")
            errors += 1
    for rel in sorted(declared):
        if rel not in scanned:
            print(f"FAIL manifest classifies a file with no retired-rail token: {rel}")
            errors += 1

    by_file: dict[str, list[int]] = {}
    for caller in manifest["callers"]:
        by_file.setdefault(caller["file"], []).extend(caller["lines"])

    for rel, entry in sorted(declared.items()):
        if entry["class"] == "non_caller":
            continue
        exempt = {row["line"] for row in entry.get("exempt_lines", [])}
        allowed = set(by_file.get(rel, [])) | exempt
        for lineno, _line in scanned.get(rel, []):
            if lineno not in allowed:
                print(f"FAIL undeclared caller line: {rel}:{lineno}")
                errors += 1
    return errors


def check_replacement(operations, record_id: str, replacement: dict, errors: list[str]) -> None:
    kind = replacement.get("kind")
    if kind not in {"operation", "official_mcp", "capability_gap", "route_policy"}:
        errors.append(f"{record_id}: replacement kind missing/invalid: {kind!r}")
        return
    if kind == "route_policy":
        if not str(replacement.get("route") or "").strip():
            errors.append(f"{record_id}: route_policy without a route")
        return
    if kind == "capability_gap":
        if not str(replacement.get("reason") or "").strip():
            errors.append(f"{record_id}: capability_gap without a reason")
        return

    operation_id = replacement.get("operation_id")
    if operation_id not in operations:
        errors.append(f"{record_id}: replacement operation not in registry: {operation_id!r}")
        return
    row = operations[operation_id]
    if kind == "official_mcp" and row.route_class != "official_mcp":
        errors.append(f"{record_id}: {operation_id} is not an official_mcp row")
    if kind == "operation" and row.route_class == "official_mcp":
        errors.append(f"{record_id}: {operation_id} is official MCP; use kind=official_mcp")
    if row.version == "v4" or row.documented_level == "S":
        errors.append(
            f"{record_id}: replacement {operation_id} is staging-only "
            f"(version={row.version}, level={row.documented_level}); never present it as production"
        )


def check_callers(manifest: dict, operations) -> int:
    errors: list[str] = []
    records = list(manifest["callers"]) + list(manifest.get("domain_references", []))
    seen = set()
    for caller in records:
        cid = caller.get("id") or "<missing id>"
        if cid in seen:
            errors.append(f"{cid}: duplicate caller id")
        seen.add(cid)

        path = ROOT / caller["file"]
        if not path.is_file():
            errors.append(f"{cid}: file missing: {caller['file']}")
            continue
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        pattern = re.compile(caller["evidence_pattern"])
        for lineno in caller["lines"]:
            if lineno < 1 or lineno > len(lines):
                errors.append(f"{cid}: line out of range {caller['file']}:{lineno}")
                continue
            if not pattern.search(lines[lineno - 1]):
                errors.append(
                    f"{cid}: evidence pattern {caller['evidence_pattern']!r} "
                    f"not on {caller['file']}:{lineno}"
                )

        replacements = caller.get("replacements") or []
        if not replacements:
            errors.append(f"{cid}: former caller has no mapped replacement")
        for replacement in replacements:
            check_replacement(operations, cid, replacement, errors)

        fallback = caller.get("fallback") or {}
        if "required" not in fallback:
            errors.append(f"{cid}: fallback.required missing")
        elif fallback["required"] and not str(fallback.get("reason") or "").strip():
            errors.append(f"{cid}: required fallback without a reason")
    for message in errors:
        print(f"FAIL {message}")
    return len(errors)


def check_alias_fixture(operations) -> int:
    path = ROOT / "tests" / "fixtures" / "ghl_compat" / "aliases.json"
    if not path.is_file():
        print("FAIL alias fixture missing")
        return 1
    fixture = json.loads(path.read_text(encoding="utf-8"))
    errors = 0
    for entry in fixture.get("community_tools", {}).get("mapped", []):
        op = entry.get("operation_id")
        if op not in operations:
            print(f"FAIL alias fixture target not in registry: {entry.get('tool')} -> {op}")
            errors += 1
            continue
        row = operations[op]
        if row.version == "v4" or row.documented_level == "S":
            fallback = entry.get("fallback_operation_id")
            note = str(entry.get("note") or "").lower()
            if not fallback or "staging" not in note:
                print(
                    f"FAIL alias fixture treats staging row as production: "
                    f"{entry.get('tool')} -> {op}"
                )
                errors += 1
    return errors


def check_matrix_document(manifest: dict, operations) -> int:
    path = ROOT / "evidence" / "W11" / "operation-routing-matrix.md"
    if not path.is_file():
        print("FAIL operation-routing-matrix.md missing")
        return 1
    text = path.read_text(encoding="utf-8")
    rows: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*([A-Z][A-Z0-9]*)\s*\|", line)
        if m:
            rows.setdefault(m.group(1), line)
    errors = 0
    for caller in manifest["callers"] + manifest.get("domain_references", []):
        cid = caller["id"]
        if f"| {cid} |" not in text:
            print(f"FAIL matrix document has no row for {cid}")
            errors += 1
            continue
        # The document's headline claim is the per-row METHOD / path / Version
        # literal. Assert it against the frozen registry instead of trusting it:
        # every operation id named in the row must have its row method and path
        # present in that same row, and its Version literal present in the row.
        row_line = rows.get(cid, "")
        cells = [c.strip() for c in row_line.split("|")]
        # cells[0] is empty (leading pipe): ID cells[1], Former caller cells[2],
        # Operation performed cells[3], Replacement cells[4], Version cells[5].
        # Assert exactly the two CLAIM columns, not prose elsewhere in the row.
        replacement_cell = cells[4] if len(cells) > 4 else ""
        version_cell = cells[5] if len(cells) > 5 else ""
        for operation_id in re.findall(r"`([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)`", replacement_cell):
            if operation_id not in operations:
                continue  # membership is reported by check_replacement for manifest ids
            row = operations[operation_id]
            if row.method not in replacement_cell or row.path_template not in replacement_cell:
                print(
                    f"FAIL matrix row {cid}: {operation_id} is {row.method} {row.path_template} "
                    f"in the registry but the Replacement cell does not state that method/path"
                )
                errors += 1
            if row.version and row.version not in version_cell:
                print(
                    f"FAIL matrix row {cid}: {operation_id} registry Version is {row.version!r} "
                    f"but the Version cell does not state it"
                )
                errors += 1
    return errors


def main() -> int:
    manifest = load_manifest()
    operations = load_registry()
    scanned = walk_text_files(manifest)
    errors = 0
    errors += check_files(manifest, scanned)
    errors += check_callers(manifest, operations)
    errors += check_matrix_document(manifest, operations)
    errors += check_alias_fixture(operations)

    callers = len(manifest["callers"])
    refs = len(manifest.get("domain_references", []))
    if errors:
        print(f"\nRESULT: FAIL ({errors} error(s)); {callers} callers, {refs} domain refs")
        return 1
    print(
        f"RESULT: PASS — {callers} former callers and {refs} domain references "
        f"all carry a mapped replacement; {len(scanned)} files classified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
