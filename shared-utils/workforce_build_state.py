#!/usr/bin/env python3
"""
Shared: workforce-build-state schema versioning + migration (U049).

Every reader and writer of .workforce-build-state.json must go through this
module so that the schema version is always checked and the file is never
silently corrupted by a version mismatch.

Use:
    from workforce_build_state import load_build_state, save_build_state, SCHEMA_VERSION

    state = load_build_state(path)
    state["someField"] = value
    save_build_state(path, state)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA_VERSION = 2
"""Current single-canonical schema version.

Version 1 = every .workforce-build-state.json that exists before U049 (no
``schemaVersion`` field).

Version 2 = additive/normalizing migration:
  - ``schemaVersion`` field added (int 2).
  - ``interviewComplete`` normalized to a strict boolean.
  - ``closeoutStatus`` defaulted to ``"pending"`` when missing.
  - Timestamp fields (``buildCompletedAt``, ``closeoutDeliveredAt``,
    ``interviewStalledAt``) normalized to ISO-8601 or omitted.
  - Top-level object identity keys (``companySlug``, ``companyName``,
    ``ownerName``, ``ownerChat``, ``departmentId``, ``departmentName``)
    ensured present with empty-string defaults.
"""


def _normalize_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return False


def _normalize_timestamp(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if "T" in stripped:
        return stripped
    return None


def _ensure_optional_string(payload: Dict[str, Any], key: str, default: str = "") -> None:
    if key not in payload:
        payload[key] = default
    elif not isinstance(payload[key], str):
        payload[key] = str(payload[key])


def migrate_v1_to_v2(state: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a v1 workforce-build-state into v2.

    Fields touched:
      - ``schemaVersion``        set to 2
      - ``interviewComplete``    normalized to boolean
      - ``closeoutStatus``       defaulted to ``"pending"`` if absent
      - ``companySlug``          defaulted to ``""``
      - ``companyName``          defaulted to ``""``
      - ``ownerName``            defaulted to ``""``
      - ``ownerChat``            defaulted to ``""``
      - ``departmentId``         defaulted to ``""``
      - ``departmentName``       defaulted to ``""``
      - ``buildCompletedAt``     normalized (non-ISO dropped)
      - ``closeoutDeliveredAt``  normalized (non-ISO dropped)
      - ``interviewStalledAt``   normalized (non-ISO dropped)
    """
    state["schemaVersion"] = 2
    state["interviewComplete"] = _normalize_boolean(state.get("interviewComplete"))

    if not isinstance(state.get("closeoutStatus"), str) or not state["closeoutStatus"].strip():
        state["closeoutStatus"] = "pending"

    _ensure_optional_string(state, "companySlug", "")
    _ensure_optional_string(state, "companyName", "")
    _ensure_optional_string(state, "ownerName", "")
    _ensure_optional_string(state, "ownerChat", "")
    _ensure_optional_string(state, "departmentId", "")
    _ensure_optional_string(state, "departmentName", "")

    for ts_key in ("buildCompletedAt", "closeoutDeliveredAt", "interviewStalledAt"):
        if ts_key in state:
            normed = _normalize_timestamp(state.get(ts_key))
            if normed is None:
                state.pop(ts_key, None)

    return state


def _quarantine_corrupt(path: Path) -> str:
    ts = int(time.time())
    quarantine = path.with_suffix(path.suffix + f".corrupt-{ts}")
    try:
        os.rename(path, quarantine)
    except OSError:
        pass
    return str(quarantine)


def load_build_state(path: Path, *, allow_absent: bool = True) -> Dict[str, Any]:
    """Read, version-check, and migrate a .workforce-build-state.json file.

    Returns {} when absent and allow_absent=True.
    Raises SystemExit(2) on corruption, SystemExit(3) on newer schema version.
    """
    if not path.exists():
        if allow_absent:
            return {}
        raise FileNotFoundError(f"{path}: workforce build state not found")

    raw = None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        quarantine = _quarantine_corrupt(path)
        print(
            f"ERROR: .workforce-build-state.json is unreadable: {exc}\n"
            f"  Quarantined to: {quarantine}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if not raw.strip():
        quarantine = _quarantine_corrupt(path)
        print(
            f"ERROR: .workforce-build-state.json is empty (zero bytes or whitespace only)\n"
            f"  Quarantined to: {quarantine}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    try:
        state = json.loads(raw)
    except json.JSONDecodeError as exc:
        quarantine = _quarantine_corrupt(path)
        print(
            f"ERROR: .workforce-build-state.json is not valid JSON: {exc}\n"
            f"  Quarantined to: {quarantine}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if not isinstance(state, dict):
        quarantine = _quarantine_corrupt(path)
        print(
            f"ERROR: .workforce-build-state.json top level is {type(state).__name__}, "
            f"not a JSON object\n  Quarantined to: {quarantine}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    file_version = state.get("schemaVersion")
    if file_version is None:
        file_version = 1

    if not isinstance(file_version, int) and not isinstance(file_version, float):
        print(
            f"ERROR: .workforce-build-state.json schemaVersion is "
            f"{type(file_version).__name__}, not an integer",
            file=sys.stderr,
        )
        raise SystemExit(2)

    file_version = int(file_version)

    if file_version > SCHEMA_VERSION:
        print(
            f"ERROR: .workforce-build-state.json has schemaVersion={file_version}, "
            f"but this reader only supports up to version {SCHEMA_VERSION}. "
            f"Refusing to parse a newer-format file with an older reader.",
            file=sys.stderr,
        )
        raise SystemExit(3)

    if file_version < SCHEMA_VERSION:
        migrated = dict(state)
        if file_version <= 1:
            migrated = migrate_v1_to_v2(migrated)
        _atomic_save(path, migrated)
        print(
            f"[workforce-build-state] Migrated {path.name} "
            f"from v{file_version} to v{SCHEMA_VERSION}",
            file=sys.stderr,
        )
        return migrated

    return state


def save_build_state(path: Path, state: Dict[str, Any]) -> None:
    """Write a workforce-build-state, always stamping the current schema version."""
    state["schemaVersion"] = SCHEMA_VERSION
    _atomic_save(path, state)


def _atomic_save(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        tmp = Path(tmp_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
    except OSError as exc:
        print(f"ERROR: could not write .workforce-build-state.json: {exc}", file=sys.stderr)
        raise


def _cli() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Workforce build-state schema migration")
    parser.add_argument("--migrate", type=Path, help="Read, migrate, and write back the state file")
    parser.add_argument("--validate", type=Path, help="Validate and print the state file as JSON")
    args = parser.parse_args()

    if args.migrate:
        try:
            state = load_build_state(args.migrate, allow_absent=True)
        except SystemExit as exc:
            raise
        if not state:
            print("ABSENT")
            raise SystemExit(1)
        print("OK")
    elif args.validate:
        state = load_build_state(args.validate, allow_absent=False)
        json.dump(state, sys.stdout, indent=2)
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    _cli()
