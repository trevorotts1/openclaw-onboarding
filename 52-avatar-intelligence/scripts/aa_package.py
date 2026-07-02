#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_package.py — deterministic deliverable assembly (Skill 52).

Consolidates the 40 stage artifacts into the 16 named deliverables (PRD 4.2) via
the 3 concatenations + 13 single-doc passes, each suffixed -<First>_<Last>.md,
plus 00-INDEX.md + MANIFEST.json. Internal-only feeders (04-07 tone styles, 38
questionnaire) are NOT published. No LLM; pure Python.

Exit 0 = ok, 2 = assembly violation, 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict


def _manifest_path() -> Path:
    return Path(__file__).resolve().parent.parent / "AA-PIPELINE-MANIFEST.json"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _words(text: str) -> int:
    return len(text.split())


def assemble(manifest: Dict[str, Any], artifacts: Dict[str, str],
             first: str, last: str, out_dir: Path) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"-{first}_{last}"
    deliverables = manifest["deliverables"]
    files: Dict[str, Any] = {}
    index_lines = [f"# Brand Intelligence Package — {first} {last}\n",
                   "16 named deliverables (37 delivered documents incl. this index + MANIFEST.json).\n"]
    for name, constituents in deliverables.items():
        parts = []
        for sid in constituents:
            txt = artifacts.get(sid, "")
            if not str(txt).strip():
                raise ValueError(f"deliverable {name}: constituent {sid} is empty/missing")
            parts.append(f"<!-- {sid} -->\n{txt.rstrip()}\n")
        body = f"# {name.replace('_',' ')}\n\n" + "\n\n---\n\n".join(parts) + "\n"
        fn = f"{name}{suffix}.md"
        (out_dir / fn).write_text(body, encoding="utf-8")
        files[fn] = {"sha256": _sha256(body), "words": _words(body), "constituents": constituents}
        index_lines.append(f"- **{fn}** — from {', '.join(constituents)}")
    (out_dir / "00-INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    man = {"package": "avatar-alchemist-brand-intelligence",
           "client_label": f"{first}_{last}", "deliverable_count": len(files),
           "files": files}
    (out_dir / "MANIFEST.json").write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    return man


# --- self-test ------------------------------------------------------------
def _synth_artifacts(manifest) -> Dict[str, str]:
    return {s["stage_id"]: f"# {s['stage_id']}\ncontent for {s['stage_id']}\n" for s in manifest["stages"]}


def run_self_test(manifest) -> int:
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "pkg"
        man = assemble(manifest, _synth_artifacts(manifest), "Jordan", "Rivers", out)
        n = man["deliverable_count"]
        if n != 16:
            ok = False; print(f"SELF-TEST FAIL: assembled {n} deliverables (expected 16).")
        else:
            print("SELF-TEST ok: assembled exactly 16 named deliverables.")
        for extra in ("00-INDEX.md", "MANIFEST.json"):
            if not (out / extra).is_file():
                ok = False; print(f"SELF-TEST FAIL: {extra} not written.")
        # internal-only feeders must NOT appear as deliverables
        allfiles = " ".join(p.name for p in out.iterdir())
        for feeder in manifest["internal_only_feeders"]:
            if feeder in allfiles:
                ok = False; print(f"SELF-TEST FAIL: internal feeder {feeder} leaked into deliverables.")
        if ok:
            print("SELF-TEST ok: index + manifest written; internal feeders excluded.")
        # missing constituent must fail closed
        try:
            bad = _synth_artifacts(manifest); bad["16-brand-bio"] = ""
            assemble(manifest, bad, "J", "R", Path(td) / "bad")
            ok = False; print("SELF-TEST FAIL: empty constituent did not raise.")
        except ValueError:
            print("SELF-TEST ok: empty constituent fails closed.")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist deliverable assembler.")
    ap.add_argument("--run-dir", help="run dir containing artifacts/<stage>.md")
    ap.add_argument("--first"); ap.add_argument("--last")
    ap.add_argument("--out", help="output deliverable folder")
    ap.add_argument("--manifest")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest or _manifest_path()).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load manifest: {exc}")
        return 3
    if args.self_test:
        return run_self_test(manifest)
    if not (args.run_dir and args.first and args.last and args.out):
        print("USAGE ERROR: --run-dir --first --last --out (or --self-test).")
        return 3
    art_dir = Path(args.run_dir) / "artifacts"
    artifacts = {p.stem: p.read_text(encoding="utf-8", errors="replace") for p in art_dir.glob("*.md")}
    try:
        man = assemble(manifest, artifacts, args.first, args.last, Path(args.out))
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 2
    print(f"assembled {man['deliverable_count']} deliverables -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
