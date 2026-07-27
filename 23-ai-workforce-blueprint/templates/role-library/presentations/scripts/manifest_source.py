#!/usr/bin/env python3
"""manifest_source.py — SINGLE CANONICAL manifest+ruleset resolver."""
from __future__ import annotations

import hashlib, sys
from pathlib import Path
from typing import NoReturn, Optional, Tuple

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
