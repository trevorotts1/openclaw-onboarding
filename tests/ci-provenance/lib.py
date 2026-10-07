"""Shared helpers for the W4-05-U1 CI/provenance/secret closure suite.

Stdlib only. No network here. Every checker writes one receipt JSON into
tests/ci-provenance/receipts/ and exits 0 (PASS), 1 (FAIL), 2 (tooling
failure — nothing was actually compared).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]          # build tree root (…/drama-song-factory-build)
RECEIPTS = HERE / "receipts"
UNIT_ID = "W4-05-U1"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_TOOLING = 2


class ToolingError(RuntimeError):
    """Missing/broken instrument. Exit 2, never a fact about the target."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_receipt(name: str, payload: dict) -> Path:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    target = RECEIPTS / name
    data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    target.write_text(data, encoding="utf-8")
    return target


def print_table(headers, rows) -> None:
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def finish(verdict: str, summary_rows, receipt: dict) -> int:
    """Print the per-family table, stamp the receipt, map verdict to exit."""
    print_table(["check", "result", "detail"], summary_rows)
    receipt["verdict"] = verdict
    receipt["finished_at"] = utcnow()
    path = write_receipt(receipt["receipt_name"], receipt)
    print("%s -> %s (receipt: %s)" % (UNIT_ID, verdict, path))
    sys.stdout.flush()
    return EXIT_PASS if verdict == "PASS" else EXIT_FAIL
