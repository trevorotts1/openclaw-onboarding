#!/usr/bin/env python3
"""test_manifest_source.py — unit tests for manifest_source.py."""
from __future__ import annotations

import hashlib, json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import manifest_source

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _make_deep_dir(base: Path, levels: int = 11) -> Path:
    deep = base
    for i in range(1, levels + 1):
        deep = deep / f"L{i}"
    deep.mkdir(parents=True, exist_ok=True)
    return deep

def _run_in_fixture(fixture_here: Path) -> subprocess.CompletedProcess:
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(HERE)!r})
from manifest_source import resolve_manifest
path, prov = resolve_manifest(Path({str(fixture_here)!r}))
print(f"path={{path}}")
print(f"provenance={{prov}}")
"""
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)

def test_installed_matching_hash():
    root = Path(tempfile.mkdtemp(prefix="test_ms_a_"))
    deep = _make_deep_dir(root)
    sops_dir = deep.parent / "sops"
    sops_dir.mkdir(parents=True, exist_ok=True)
    manifest_data = json.dumps({"manifest_version": 99, "phases": [], "autofails": [], "roles": []})
    mp = sops_dir / "PIPELINE-MANIFEST.json"
    mp.write_text(manifest_data)
    cs = _sha256(manifest_data.encode())
    (sops_dir / "MANIFEST-SOURCE.txt").write_text(f"source_path=x\ngit_sha=\ncontent_sha256={cs}\ninstalled_at=1970-01-01T00:00:00Z\n")
    proc = _run_in_fixture(deep)
    assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr}"
    assert "provenance=installed" in proc.stdout

def test_installed_mismatched_hash():
    root = Path(tempfile.mkdtemp(prefix="test_ms_b_"))
    deep = _make_deep_dir(root)
    sops_dir = deep.parent / "sops"
    sops_dir.mkdir(parents=True, exist_ok=True)
    mp = sops_dir / "PIPELINE-MANIFEST.json"
    mp.write_text(json.dumps({"manifest_version": 99, "phases": [], "autofails": [], "roles": []}))
    (sops_dir / "MANIFEST-SOURCE.txt").write_text("source_path=x\ngit_sha=\ncontent_sha256=0000000000000000000000000000000000000000000000000000000000000000\ninstalled_at=1970-01-01T00:00:00Z\n")
    proc = _run_in_fixture(deep)
    assert proc.returncode == 2, f"expected exit 2, got {proc.returncode}"
    assert "FATAL (manifest provenance)" in proc.stderr

def test_cluster_found():
    root = Path(tempfile.mkdtemp(prefix="test_ms_c_"))
    deep = _make_deep_dir(root, levels=4)
    cluster = root / "universal-sops" / "presentation-slide-craft"
    cluster.mkdir(parents=True, exist_ok=True)
    (cluster / "PIPELINE-MANIFEST.json").write_text(json.dumps({"manifest_version": 25}))
    proc = _run_in_fixture(deep)
    assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr}"
    assert "provenance=cluster" in proc.stdout

def test_decoy_universal_sops_rejected():
    root = Path(tempfile.mkdtemp(prefix="test_ms_d_"))
    deep = _make_deep_dir(root, levels=11)
    decoy = root / "L1" / "L2" / "L3" / "L4" / "universal-sops"
    decoy.mkdir(parents=True, exist_ok=True)
    (decoy / "some-other-file.txt").write_text("decoy")
    cluster = root / "universal-sops" / "presentation-slide-craft"
    cluster.mkdir(parents=True, exist_ok=True)
    cm = cluster / "PIPELINE-MANIFEST.json"
    cm.write_text(json.dumps({"manifest_version": 25}))
    proc = _run_in_fixture(deep)
    assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr}"
    assert "provenance=cluster" in proc.stdout
    assert str(decoy) not in proc.stdout

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q", "-v"]))
