"""Provenance manifest for the packaged persona closure (PRES-053)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Dict, List

PROVENANCE_FILENAME = "SOURCE-PROVENANCE.json"


def git_blob_sha(repo: Path, relpath: str, rev: str = "HEAD") -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", f"{rev}:{relpath}"],
            capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def build_provenance(repo: Path, resource_root: Path,
                     resource_files: List[str],
                     source_files: List[str],
                     rev: str = "HEAD") -> dict:
    resources: Dict[str, dict] = {}
    for rel in sorted(resource_files):
        p = resource_root / rel
        resources[rel] = {
            "file_sha256": file_sha(p),
            "git_blob_sha": git_blob_sha(
                repo, str(Path("22-book-to-persona-coaching-leadership-system") / rel
                           if (resource_root.name == "personas") else rel), rev),
        }
    sources: Dict[str, dict] = {}
    for rel in sorted(source_files):
        sources[rel] = {
            "git_blob_sha": git_blob_sha(repo, rel, rev),
        }
    return {
        "task": "PRES-053",
        "rev": rev,
        "resource_root": str(resource_root),
        "resources": resources,
        "vendored_sources": sources,
    }


def write_provenance(path: Path, manifest: dict) -> Path:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path
