#!/usr/bin/env python3
"""manifest_assert.py -- assert the deployed manifest matches its recorded source (MASTER-SPEC FILE 10).

Five checks, each printed as a [PASS]/[FAIL] line:

  1. deployed manifest exists and parses (read_deployed_manifest)
  2. MANIFEST-SOURCE.txt hash matches the deployed file (compute_sha256 +
     read_manifest_source + assert_hash_match)
  3. manifest_version is current (assert_version -- no stale fork)
  4. phase count is current (assert_phase_count)
  5. all AF-SP-* gate codes present (assert_af_sp_codes)

run_sync_check() runs all five and returns True iff every check passed.
main() prints 5 lines and exits 0 (all pass) or 1 (any fail).

Usage:
  python3 manifest_assert.py --sops-dir <sops> --scripts-dir <scripts>
Defaults: scripts-dir = this file's directory; sops-dir = <scripts-dir>/../sops.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# The canonical manifest floor, mirrored from presentation_job/manifest.py
# (MIN_MANIFEST_VERSION). Bump the two TOGETHER -- a floor one behind the
# manifest is the split-brain this check exists to prevent.
# 48 -> 49: heartbeat-ceiling repair -- 13 phases' heartbeat_minutes tightened to
# fit their own PHASE_BUDGET_MINUTES (E3 drift repair); see presentation_job/manifest.py
# for the full rationale. MIN follows the manifest in the same commit (U019 step 8).
# 49 -> 50: P-QC-AGGREGATE step-contract repair -- sync_check.py's W1 warning
# ("phase P-QC-AGGREGATE declares no verifier") flagged the one phase of 36 that
# never declared `verifier` in PIPELINE-MANIFEST.json (its `executor` was already
# present). Declared "verifier": "phase_verifiers.verify" -- the identical value
# every other phase already carries, and phase_verifiers.py already registers a
# P-QC-AGGREGATE entry (qc:final) in its dispatch table, so the implementation was
# ready and only the manifest declaration was missing. Content-only edit; no new
# phase/AF code. MIN follows the manifest in the same commit (U019 step 8).
# 49 -> 50: min_bytes split-brain reconciliation (2026-08-18) -- speech_pdf and
# teleprompter_html carried orphaned pre-doctrine values (20480 / 10240, dated
# 2026-06-17, predating the 2026-07-12 SOP reconciliation) that disagreed with
# deliverables.py / build_deck.py's already-reconciled floors (3000 / 20000).
# Content-only edit to two existing entries, same class of change as WI-10
# (44 -> 45); MIN follows the manifest in the same commit.
MIN_MANIFEST_VERSION = 50
MIN_MANIFEST_PHASES = 36
MIN_AF_SP_CODES = 16


# ---------------------------------------------------------------------------
# Reads + hashing
# ---------------------------------------------------------------------------
def read_deployed_manifest(sops_dir: str | Path) -> dict:
    """Load the deployed PIPELINE-MANIFEST.json. Raises FileNotFoundError /
    ValueError (unparsable) on failure -- the caller turns that into a FAIL."""
    path = Path(sops_dir) / "PIPELINE-MANIFEST.json"
    if not path.is_file():
        raise FileNotFoundError(f"deployed manifest not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compute_sha256(path: str | Path) -> str:
    """SHA-256 of the file at path (lowercase hex)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest_source(sops_dir: str | Path) -> Dict[str, str]:
    """Parse MANIFEST-SOURCE.txt (key=value lines) beside the manifest."""
    path = Path(sops_dir) / "MANIFEST-SOURCE.txt"
    if not path.is_file():
        raise FileNotFoundError(f"MANIFEST-SOURCE.txt not found at {path}")
    record: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            record[k.strip()] = v.strip()
    return record


# ---------------------------------------------------------------------------
# Assertions -- each returns (label, ok, detail)
# ---------------------------------------------------------------------------
def assert_hash_match(sops_dir: str | Path) -> Tuple[str, bool, str]:
    """Deployed manifest's SHA-256 equals the content_sha256 recorded in
    MANIFEST-SOURCE.txt."""
    try:
        manifest_path = Path(sops_dir) / "PIPELINE-MANIFEST.json"
        actual = compute_sha256(manifest_path)
        record = read_manifest_source(sops_dir)
    except (FileNotFoundError, OSError) as exc:
        return "hash-match", False, str(exc)
    recorded = record.get("content_sha256", "")
    if not recorded:
        return "hash-match", False, "MANIFEST-SOURCE.txt has no content_sha256 line"
    ok = recorded == actual
    detail = f"sha256 {actual[:12]}… recorded {recorded[:12]}… {'match' if ok else 'MISMATCH'}"
    return "hash-match", ok, detail


def assert_version(sops_dir: str | Path) -> Tuple[str, bool, str]:
    """manifest_version >= MIN_MANIFEST_VERSION (no stale fork)."""
    try:
        manifest = read_deployed_manifest(sops_dir)
    except (FileNotFoundError, ValueError) as exc:
        return "version", False, str(exc)
    version = manifest.get("manifest_version")
    if not isinstance(version, int):
        return "version", False, f"manifest_version is not an int: {version!r}"
    ok = version >= MIN_MANIFEST_VERSION
    detail = f"manifest_version {version} >= floor {MIN_MANIFEST_VERSION}"
    return "version", ok, detail


def assert_phase_count(sops_dir: str | Path) -> Tuple[str, bool, str]:
    """phase count >= MIN_MANIFEST_PHASES."""
    try:
        manifest = read_deployed_manifest(sops_dir)
    except (FileNotFoundError, ValueError) as exc:
        return "phase-count", False, str(exc)
    phases = manifest.get("phases") or []
    count = len(phases) if isinstance(phases, list) else 0
    ok = count >= MIN_MANIFEST_PHASES
    detail = f"{count} phases >= floor {MIN_MANIFEST_PHASES}"
    return "phase-count", ok, detail


def assert_af_sp_codes(sops_dir: str | Path) -> Tuple[str, bool, str]:
    """Every AF-SP-* gate code the signature pipeline requires is registered."""
    try:
        manifest = read_deployed_manifest(sops_dir)
    except (FileNotFoundError, ValueError) as exc:
        return "af-sp-codes", False, str(exc)
    autofails = manifest.get("autofails") or []
    codes = [str(a.get("code", "")) for a in autofails if isinstance(a, dict)]
    af_sp = sorted(c for c in codes if c.startswith("AF-SP-"))
    ok = len(af_sp) >= MIN_AF_SP_CODES
    detail = f"{len(af_sp)} AF-SP-* codes >= floor {MIN_AF_SP_CODES}"
    return "af-sp-codes", ok, detail


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def assert_deployed(sops_dir: str | Path) -> Tuple[str, bool, str]:
    """The deployed manifest exists, parses, and MANIFEST-SOURCE.txt sits beside it."""
    manifest_path = Path(sops_dir) / "PIPELINE-MANIFEST.json"
    if not manifest_path.is_file():
        return "deployed", False, f"deployed manifest not found at {manifest_path}"
    source_path = Path(sops_dir) / "MANIFEST-SOURCE.txt"
    if not source_path.is_file():
        return "deployed", False, f"MANIFEST-SOURCE.txt not found at {source_path}"
    try:
        manifest = read_deployed_manifest(sops_dir)
    except ValueError as exc:
        return "deployed", False, f"deployed manifest does not parse: {exc}"
    version = manifest.get("manifest_version")
    detail = (f"manifest present and parses (manifest_version={version!r}, "
              f"{len(manifest.get('phases') or [])} phases), source record present")
    return "deployed", True, detail


def run_sync_check(sops_dir: str | Path, scripts_dir: str | Path | None = None) -> bool:
    """Run all five manifest checks. Returns True iff every check passed.

    scripts_dir is accepted for interface symmetry with the deployment layout
    (sops_dir defaults relative to it); the checks themselves only need sops_dir.
    """
    checks = [
        assert_deployed(sops_dir),
        assert_hash_match(sops_dir),
        assert_version(sops_dir),
        assert_phase_count(sops_dir),
        assert_af_sp_codes(sops_dir),
    ]
    ok_all = True
    for label, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            ok_all = False
        print(f"[{mark}] {label}: {detail}", flush=True)
    return ok_all


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="manifest_assert.py",
        description="Assert the deployed manifest matches its recorded source (MASTER-SPEC FILE 10). "
                    "Prints 5 [PASS]/[FAIL] lines; exit 0 iff all pass.",
    )
    p.add_argument("--sops-dir", type=Path,
                   help="directory holding PIPELINE-MANIFEST.json and MANIFEST-SOURCE.txt "
                        "(default: <scripts-dir>/../sops)")
    p.add_argument("--scripts-dir", type=Path, default=Path(__file__).resolve().parent,
                   help="scripts directory (default: this file's directory)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    sops_dir = args.sops_dir or (args.scripts_dir / ".." / "sops")
    sops_path = Path(sops_dir).expanduser().resolve()
    try:
        ok = run_sync_check(sops_path, args.scripts_dir)
    except Exception as exc:  # noqa: BLE001 -- a crash must still produce a FAIL line
        print(f"[FAIL] sync-check crashed: {exc}", file=sys.stderr)
        return 1
    print("SYNC-CHECK: " + ("ALL PASS" if ok else "FAILURES PRESENT"), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
