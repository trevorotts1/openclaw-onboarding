#!/usr/bin/env python3
"""Fail-closed pre-flight validation for the Podbean publish webhook payload.

Usage:
    python3 validate_podcast_publish_payload.py payload.json
    printf '%s' "$PAYLOAD_JSON" | python3 validate_podcast_publish_payload.py

Exit 0 is silent and means all required fields are present and non-empty.
Exit 1 means one or more required fields are missing, null, or empty.
Exit 2 means the input could not be read as a JSON object.

This script performs no network calls and prints no payload values.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_INVALID_PAYLOAD = 1
EXIT_INPUT_ERROR = 2

REQUIRED_FIELDS = (
    "podcast_id",
    "audio_url",
    "image_url",
    "title",
    "description",
    "publish_date",
    "client_email",
)


def _is_empty(value: Any) -> bool:
    """Return True only for null or values with no usable content."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def validate_payload(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (missing_fields, invalid_fields) in canonical field order."""
    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    invalid = [
        field for field in REQUIRED_FIELDS
        if field in payload and _is_empty(payload[field])
    ]
    return missing, invalid


def _load_payload(path: str | None) -> dict[str, Any]:
    if path and path != "-":
        raw = Path(path).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        raise ValueError("input is empty")

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value must be an object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the seven required Podbean publish webhook fields before POSTing. "
            "No network calls are made."
        )
    )
    parser.add_argument(
        "payload",
        nargs="?",
        help="JSON payload file (default: stdin; use '-' explicitly for stdin)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _load_payload(args.payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"podcast payload pre-flight input error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    missing, invalid = validate_payload(payload)
    if missing or invalid:
        problems = []
        if missing:
            problems.append("missing: " + ", ".join(missing))
        if invalid:
            problems.append("null/empty: " + ", ".join(invalid))
        print(
            "podcast payload pre-flight failed; " + "; ".join(problems),
            file=sys.stderr,
        )
        return EXIT_INVALID_PAYLOAD

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
