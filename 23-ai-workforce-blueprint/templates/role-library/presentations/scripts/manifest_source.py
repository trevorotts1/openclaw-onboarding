#!/usr/bin/env python3
"""manifest_source.py — SINGLE CANONICAL manifest+ruleset resolver."""
from __future__ import annotations

import hashlib, json, sys
from pathlib import Path
from typing import Any, Dict, NoReturn, Optional, Tuple

def refuse(msg: str) -> NoReturn:
    print(f"FATAL (manifest provenance): {msg}", file=sys.stderr)
    sys.exit(2)

def find_repo_root(start: Path) -> Optional[Path]:
    cur = start
    for _ in range(12):
        candidate = cur / "universal-sops"
        if candidate.is_dir() and (candidate / "presentation-slide-craft" / "PIPELINE-MANIFEST.json").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

# ---------------------------------------------------------------------------
# FIX 32 — REAL MANIFEST-COPY DRIFT DETECTOR (content hash, not version number)
# ---------------------------------------------------------------------------
# BROKEN (verified 2026-08-31, this box): the repo cluster copy
# (universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json) and the
# materialized department copy (~/.openclaw/workspace/departments/Presentations/
# sops/PIPELINE-MANIFEST.json) differ at the SAME version number — the repo copy
# is v52 (sha 8507f9d1...) while the materialized copy is v51 (sha 6140fb52...)
# and v51's own recorded MANIFEST-SOURCE.txt hash MATCHES its file, so every
# existing per-copy provenance check passes on both copies simultaneously. Each
# copy is internally consistent; the TWO copies disagree, and nothing anywhere
# compares them. The manifest_version field cannot detect this: a one-field
# content edit leaves the version number untouched (that is exactly how the
# live drift arose — same "51", different bytes).
#
# The comparison below is a CONTENT hash, not a byte hash:
#   canonical_json_sha256() parses the manifest and re-serializes with sorted
#   keys and no insignificant whitespace (json.dumps(obj, sort_keys=True,
#   separators=(",",":"))). Two copies that differ ONLY by indentation, key
#   order, or trailing whitespace hash EQUAL — a pure reformat is not drift.
#   Any change to a value, however small (one label field), hashes DIFFERENT.
#
# Rollback: callers gate this behind PRESENTATION_MANIFEST_COPY_DRIFT=0
# (default 1 = ON). The disabled path is documented at every call site: it
# skips the copy comparison and reports the skip, never silently pretends an
# unverified copy was verified.
# ---------------------------------------------------------------------------

def canonical_json_sha256(obj: Any) -> str:
    """Content hash of a parsed JSON object: sorted keys, no insignificant
    whitespace. A byte-level reformat of the same JSON hashes identically; a
    one-field value change hashes differently."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()

def _load_manifest_json(path) -> Any:
    p = Path(path)
    if not p.is_file():
        refuse(f"manifest copy not found at {p} — FIX 32 copy comparison cannot run")
    try:
        return json.loads(p.read_text())
    except Exception:
        refuse(f"manifest copy {p} is not valid JSON — FIX 32 copy comparison cannot run")

def compare_manifest_copies(primary: str, peer: str) -> Dict[str, Any]:
    """Compare two PIPELINE-MANIFEST.json copies by canonical-JSON content hash.

    Returns {"drift": False, ...} when the two copies hold identical JSON
    content (byte-level reformat differences excluded by canonical hashing),
    {"drift": True, ...} naming both copies, both canonical hashes, and both
    manifest_version numbers when they differ.

    The version numbers are reported, never compared: "same version, different
    bytes" is the exact live broken state this detector exists to catch, so
    EQUAL version numbers must not suppress the drift verdict, and UNEQUAL
    ones are surfaced as detail, not treated as an explanation.
    """
    prim_path, peer_path = Path(primary), Path(peer)
    prim_obj = _load_manifest_json(prim_path)
    peer_obj = _load_manifest_json(peer_path)
    prim_sha = canonical_json_sha256(prim_obj)
    peer_sha = canonical_json_sha256(peer_obj)
    prim_ver = prim_obj.get("manifest_version") if isinstance(prim_obj, dict) else None
    peer_ver = peer_obj.get("manifest_version") if isinstance(peer_obj, dict) else None
    return {
        "drift": prim_sha != peer_sha,
        "primary": str(prim_path),
        "peer": str(peer_path),
        "primary_sha256": prim_sha,
        "peer_sha256": peer_sha,
        "primary_version": prim_ver,
        "peer_version": peer_ver,
        "same_version_number": prim_ver == peer_ver,
    }

def resolve_manifest(here: Path) -> Tuple[Path, str]:
    sops_dir = here.parent / "sops"
    source_txt = sops_dir / "MANIFEST-SOURCE.txt"
    manifest_path = sops_dir / "PIPELINE-MANIFEST.json"
    if source_txt.exists():
        try:
            record = {}
            for line in source_txt.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    record[k.strip()] = v.strip()
        except Exception:
            refuse("MANIFEST-SOURCE.txt is present but unreadable")
        expected = record.get("content_sha256", "")
        if not manifest_path.exists():
            refuse(f"MANIFEST-SOURCE.txt records content_sha256={expected} but PIPELINE-MANIFEST.json does not exist at {manifest_path}")
        actual = _sha256(manifest_path)
        if actual != expected:
            refuse(f"MANIFEST-SOURCE.txt records content_sha256={expected} but {manifest_path} has content_sha256={actual} — the installed manifest does not match the recorded hash. The file may have been replaced without updating MANIFEST-SOURCE.txt.")
        return manifest_path, "installed"
    root = find_repo_root(here)
    if root is not None:
        cluster_manifest = root / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cluster_manifest.exists():
            return cluster_manifest, "cluster"
    if manifest_path.exists():
        return manifest_path, "legacy"
    pres_manifest = here.parent / "PIPELINE-MANIFEST.json"
    if pres_manifest.exists():
        return pres_manifest, "legacy"
    refuse("PIPELINE-MANIFEST.json not found (looked in sops/, presentations/, and cluster walk-up)")
    return manifest_path, "legacy"

def resolve_ruleset(here: Path) -> Tuple[Path, str]:
    sops_dir = here.parent / "sops"
    source_txt = sops_dir / "MANIFEST-SOURCE.txt"
    if source_txt.exists():
        installed_ruleset = sops_dir / "MASTER-QC-AUTOFAIL-RULESET.md"
        if installed_ruleset.exists():
            return installed_ruleset, "installed"
    root = find_repo_root(here)
    if root is not None:
        cluster_ruleset = root / "universal-sops" / "presentation-slide-craft" / "MASTER-QC-AUTOFAIL-RULESET.md"
        if cluster_ruleset.exists():
            return cluster_ruleset, "cluster"
    candidates = [sops_dir / "SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md", sops_dir / "MASTER-QC-AUTOFAIL-RULESET.md", here.parent / "MASTER-QC-AUTOFAIL-RULESET.md"]
    for c in candidates:
        if c.exists():
            return c, "legacy"
    refuse("MASTER-QC-AUTOFAIL-RULESET.md not found (looked in sops/, presentations/, and cluster walk-up)")
    return candidates[0], "legacy"
