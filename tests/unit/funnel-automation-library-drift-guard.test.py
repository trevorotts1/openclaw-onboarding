#!/usr/bin/env python3
"""Unit test for scripts/check-funnel-automation-library-drift.py — the TEMPLATE COUNT PIN.

WHY THIS EXISTS
---------------
The guard's set comparisons (disk - idx, idx - disk) only see ONE-SIDED drift. If a
template file AND its catalog-index.json row disappear together, both sides agree with
each other and the guard goes green on a smaller library. That was the real hole: at
parent commit d810b764c the automation check was `len(disk) != len(idx)` — a tautology
once both sides lose the same row.

c2e0f680c restored a real floor (EXPECTED_TEMPLATE_COUNT) checked against BOTH
len(idx) and len(disk). This test is the non-vacuity proof for that fix: it performs
the EXACT symmetric deletion the parent missed, and fails if the guard stops biting.

Run:
    python3 tests/unit/funnel-automation-library-drift-guard.test.py

Exit 0 = pass, 1 = fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).parent          # tests/unit/
_REPO = _HERE.parent.parent            # repo root
_GUARD = _REPO / "scripts" / "check-funnel-automation-library-drift.py"
assert _GUARD.is_file(), f"guard not found at {_GUARD}"

_AUTO = Path("44-convert-and-flow-operator") / "automation-templates"
_FUNNELS = Path("06-ghl-install-pages") / "funnel-templates"
_TOOLS = Path("06-ghl-install-pages") / "tools"
_INDEX = _AUTO / "_matcher" / "catalog-index.json"
_LINKS = _AUTO / "_links" / "funnel-to-automation.json"
_CANONICAL = Path("22-book-to-persona-coaching-leadership-system") / "persona-categories.json"

# Same set the guard skips: files in a template group that are not templates.
_NON_TEMPLATES = frozenset({"automation-build.schema.json", "text-sets.json"})


def _copy_inputs(dest: Path) -> Path:
    """Mirror every input the guard reads into `dest` and return the guard path there.

    Only these trees are needed; the guard resolves everything else relative to its
    own repo root (here: `dest`).
    """
    (dest / "scripts").mkdir(parents=True)
    shutil.copy2(_GUARD, dest / "scripts" / _GUARD.name)
    shutil.copytree(_REPO / _AUTO, dest / _AUTO)
    shutil.copytree(_REPO / _FUNNELS, dest / _FUNNELS)
    shutil.copytree(_REPO / _TOOLS, dest / _TOOLS)
    shutil.copytree(_REPO / "shared-utils", dest / "shared-utils")
    (dest / _CANONICAL).parent.mkdir(parents=True)
    shutil.copy2(_REPO / _CANONICAL, dest / _CANONICAL)
    return dest / "scripts" / _GUARD.name


def _run(guard: Path) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(guard)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def _disk_map(root: Path) -> dict[str, Path]:
    """{'group/id': path} for every template .json on disk, mirroring the guard."""
    out: dict[str, Path] = {}
    for gdir in sorted(root.iterdir()):
        if not gdir.is_dir() or gdir.name.startswith("_"):
            continue
        for f in sorted(gdir.iterdir()):
            if not f.suffix == ".json" or f.name.startswith("_") or f.name in _NON_TEMPLATES:
                continue
            tid = json.loads(f.read_text(encoding="utf-8")).get("id") or f.stem
            out[f"{gdir.name}/{tid}"] = f
    return out


def _linked_automations(repo: Path) -> set[str]:
    """The 'category/id' set the funnel link map references."""
    links = json.loads((repo / _LINKS).read_text(encoding="utf-8"))
    refs: set[str] = set()
    for link in links.get("links", []):
        candidates = [link.get("primary_followup")] + list(link.get("secondary_followups", []))
        if "graduation_followup" in link:
            candidates.append(link["graduation_followup"])
        for ref in candidates:
            if ref:
                refs.add(f"{ref.get('category')}/{ref.get('automation_id')}")
    return refs


def _drop_row(index_path: Path, victim: str) -> None:
    doc = json.loads(index_path.read_text(encoding="utf-8"))
    doc["templates"] = [t for t in doc.get("templates", [])
                        if f"{t['group']}/{t['id']}" != victim]
    index_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="drift-guard-test-") as tmp:
        repo = Path(tmp) / "repo"
        guard = _copy_inputs(repo)

        # (b) the untouched copy is clean
        rc, out = _run(guard)
        assert rc == 0, f"clean copy must exit 0, got {rc}:\n{out}"

        auto_root = repo / _AUTO
        index_path = repo / _INDEX
        disk = _disk_map(auto_root)
        linked = _linked_automations(repo)
        # PITFALL: a referenced victim also trips the link-map check and confounds the
        # proof, so only ever choose a template the link map does not mention.
        victims = sorted(set(disk) - linked)
        assert victims, "no unreferenced automation template to use as the victim"
        victim = victims[0]
        victim_path = disk[victim]

        file_bytes = victim_path.read_bytes()
        index_bytes = index_path.read_bytes()

        # (c) symmetric loss: the file and its index row both vanish
        victim_path.unlink()
        _drop_row(index_path, victim)
        rc, out = _run(guard)
        assert rc == 1, f"symmetric deletion must exit 1, got {rc}:\n{out}"
        assert "count drift" in out, (
            f"symmetric deletion must be named as count drift, got:\n{out}")
        assert "BROKEN automation ref" not in out, (
            f"victim {victim} is link-map referenced; proof is confounded:\n{out}")

        # (d) restore both -> clean again
        victim_path.write_bytes(file_bytes)
        index_path.write_bytes(index_bytes)
        rc, out = _run(guard)
        assert rc == 0, f"after restore the guard must exit 0, got {rc}:\n{out}"

        # (e) one-sided loss: file gone, row kept -> orphan + phantom
        victim_path.unlink()
        rc, out = _run(guard)
        assert rc == 1, f"file-only deletion must exit 1, got {rc}:\n{out}"
        assert "phantom" in out or "orphan" in out, (
            f"file-only deletion must name a phantom/orphan, got:\n{out}")
        assert victim in out, f"guard output must name {victim}, got:\n{out}"
        victim_path.write_bytes(file_bytes)

    print("OK — drift guard exits 0 clean, 1 on symmetric (file + row) loss naming count "
          "drift, 0 after restore, 1 on one-sided loss naming the phantom.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAIL — {exc}")
        raise SystemExit(1)
