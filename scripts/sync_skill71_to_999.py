#!/usr/bin/env python3
"""Sync engine for scripts/sync-skill71-to-999.sh (fix plan Item 27).

Direction is onboarding to 999, always. The sync:
  - refuses when the two skill-version.txt MAJOR versions differ;
  - refuses while an onb_only file (two_strike_adapter.py) is present
    in the 999 tree (removing it is a human act, never the sync's);
  - copies neutral-class files byte for byte (skill tree and the
    tracked repo-level files: the vendored enforcer and the
    frontmatter-version guard);
  - copies GHL pack files whose pack-manifest class is neutral;
  - regenerates references/kie-policy-999.json from the onboarding
    gate's constants (Item 28 Row 3; generated at sync, never authored
    in 999);
  - never touches adapter-class, version, or changelog files in 999:
    those are maintained per harness and reported by the parity check
    that runs at the end;
  - never touches the 999-only modules (scripts/kie_transport.py,
    scripts/agnes_route.py, scripts/vercel_deploy.py): they are
    authored for the 999 edition and versioned in that repo.

Exit codes: 0 synced and parity holds, 1 refused or parity failures,
2 usage or config error.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The checker ships under a hyphenated CLI name (check-skill71-parity.py),
# so it is loaded by path rather than imported by module name.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "check_skill71_parity",
    Path(__file__).resolve().parent / "check-skill71-parity.py")
_parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_parity)
ALLOWLIST_REL = _parity.ALLOWLIST_REL
PACK_MANIFEST_REL = _parity.PACK_MANIFEST_REL
SKILL_999 = _parity.SKILL_999
SKILL_ONB = _parity.SKILL_ONB
classify = _parity.classify
major_of = _parity.major_of
policy_payload = _parity.policy_payload

GENERATOR = "scripts/sync_skill71_to_999.py (Item 27 sync)"


def copy_file(src: Path, dst: Path, dry: bool, log: list):
    if dst.is_file() and dst.read_bytes() == src.read_bytes():
        return
    log.append(f"copy {src} -> {dst}")
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sync Skill 71 from onboarding to 999 (Item 27).")
    ap.add_argument("--onb-root", type=Path, required=True)
    ap.add_argument("--nine-root", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    dry = args.dry_run

    onb_skill = args.onb_root / SKILL_ONB
    nine_skill = args.nine_root / SKILL_999
    if not onb_skill.is_dir() or not nine_skill.is_dir():
        print(f"REFUSED: skill tree missing (onb: {onb_skill}, 999: {nine_skill})")
        return 2
    allow = json.loads((onb_skill / ALLOWLIST_REL).read_text(encoding="utf-8"))
    classes = allow.get("classes", {})

    om = major_of((onb_skill / "skill-version.txt").read_text(encoding="utf-8"))
    nm_path = nine_skill / "skill-version.txt"
    nm = major_of(nm_path.read_text(encoding="utf-8")) if nm_path.is_file() else None
    if om is None or nm is None or om != nm:
        print(f"REFUSED: skill-version major mismatch (onboarding {om!r}, 999 {nm!r}); "
              f"bump the 999 edition's major deliberately before syncing")
        return 1

    log = []
    for rel in classes.get("onb_only", {}).get("globs", []):
        if (nine_skill / rel).is_file():
            print(f"REFUSED: onb_only file present in the 999 tree: {rel}; "
                  f"remove it by hand (it must never cross), then re-run the sync")
            return 1

    for p in sorted(onb_skill.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = str(p.relative_to(onb_skill))
        if classify(rel, classes) == "neutral":
            copy_file(p, nine_skill / rel, dry, log)

    for entry in allow.get("tracked_repo_files", []):
        src = args.onb_root / entry["path"]
        if src.is_file():
            copy_file(src, args.nine_root / entry["path"], dry, log)
        else:
            print(f"REFUSED: tracked source missing in onboarding: {entry['path']}")
            return 1

    pack = json.loads((onb_skill / PACK_MANIFEST_REL).read_text(encoding="utf-8"))
    for item in pack.get("files", []):
        if item.get("verdict") == "exclude" or item.get("class") != "neutral":
            continue
        src = args.onb_root / item["source"]
        if src.is_file():
            copy_file(src, args.nine_root / item["dest"], dry, log)

    gate_path = onb_skill / "scripts" / "stage_gate.py"
    payload = policy_payload(gate_path.read_text(encoding="utf-8"))
    payload["generated_by"] = GENERATOR
    payload["source_gate_sha256"] = hashlib.sha256(gate_path.read_bytes()).hexdigest()
    gen_dst = nine_skill / "references" / "kie-policy-999.json"
    gen_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if not gen_dst.is_file() or gen_dst.read_text(encoding="utf-8") != gen_text:
        log.append(f"generate {gen_dst}")
        if not dry:
            gen_dst.parent.mkdir(parents=True, exist_ok=True)
            gen_dst.write_text(gen_text, encoding="utf-8")

    for line in log:
        print(("DRY " if dry else "") + line)
    print(f"{'would copy' if dry else 'copied'}: {len(log)} file(s)")
    if dry:
        return 0
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "check-skill71-parity.py"),
         "--onb-root", str(args.onb_root), "--nine-root", str(args.nine_root)],
        text=True, capture_output=True)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr, end="")
        print("SYNC DONE, PARITY FAILURES REMAIN (adapter drift is reported, not synced)")
        return 1
    print("SYNC DONE, PARITY PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
