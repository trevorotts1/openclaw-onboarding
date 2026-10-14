#!/usr/bin/env python3
"""Skill 71 cross-repo parity checker (fix plan Item 27).

Compares the onboarding Skill 71 tree against the 999 (Claude Code
harness) edition, file by file, under the classification in the skill's
repo-integration/skill71-sync-allowlist.json:

  neutral      byte-parity required
  adapter      must exist in both; the diff is reported, never failed
               (the two harnesses legitimately differ there: engine
               defaults per Amendment 5B, runner profiles, route text,
               SKILL.md's onboarding-only gate section)
  version      per-repo files; parity requires matching MAJOR versions
  changelog    per-repo; reported only
  onb_only     must be ABSENT in 999 (two_strike_adapter.py)
  nine_only    must be PRESENT in 999 (the vendored route modules)
  generated    recomputed from the onboarding sources; any payload
               difference beyond the generation stamp fails
  tracked      repo-level files compared across the two repo roots
               (the vendored enforcer, the frontmatter guard)
  GHL pack     per-file classes from repo-integration/
               ghl-pack-manifest.json (neutral byte-parity, adapter
               version-tracked, excluded must be absent in 999)

Anything the checker cannot classify, and any drift in a byte-parity
class, FAILS. Adapter-class differences are reported as a version
-tracked diff summary (files, lines added, lines removed).

Usage:
  check-skill71-parity.py --onb-root DIR --nine-root DIR [--json PATH]

Exit codes: 0 parity holds, 1 parity failures, 2 usage or config error.
No network, no credentials; file bytes only.
"""
import argparse
import ast
import fnmatch
import hashlib
import json
import sys
from pathlib import Path

SKILL_ONB = "71-blackceo-signature-page"
SKILL_999 = ".claude/skills/blackceo-signature-page"
ALLOWLIST_REL = "repo-integration/skill71-sync-allowlist.json"
PACK_MANIFEST_REL = "repo-integration/ghl-pack-manifest.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify(rel: str, classes: dict) -> str:
    for name in ("onb_only", "nine_only", "generated", "version",
                 "changelog", "adapter", "tracked"):
        spec = classes.get(name)
        if spec and any(fnmatch.fnmatch(rel, g) for g in spec.get("globs", [])):
            return name
    return "neutral"


def diff_counts(a: bytes, b: bytes) -> tuple:
    import difflib
    al = a.decode("utf-8", errors="replace").splitlines()
    bl = b.decode("utf-8", errors="replace").splitlines()
    added = removed = 0
    for line in difflib.unified_diff(al, bl, lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def major_of(text: str):
    t = text.strip().lstrip("vV")
    head = t.split(".")[0]
    return head if head.isdigit() else None


def policy_payload(gate_source: str) -> dict:
    """The kie-policy-999.json payload, recomputed from the onboarding
    gate's own constants (Item 28 Row 3). Department pin becomes user
    pin in the 999 vocabulary."""
    tree = ast.parse(gate_source)
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("N43_SUBSTITUTIONS", "N43_LEGACY_ONLY", "MODEL_SOURCES"):
                found[name] = ast.literal_eval(node.value)
    sources = [("user-pin" if s == "department-pin" else s)
               for s in found.get("MODEL_SOURCES", [])]
    return {
        "n43_substitutions": found.get("N43_SUBSTITUTIONS", {}),
        "n43_legacy_only": list(found.get("N43_LEGACY_ONLY", [])),
        "model_sources": sources,
        "model_source_note": ("In the 999 edition the pin that names where a model "
                              "id came from is the user's own pin (recorded as "
                              "user-pin); the onboarding edition records the same "
                              "fact as department-pin. The gate accepts user-pin on "
                              "claude-nine runs under the Item 28 step 3 alias."),
        "precedence": ["explicit request", "user pin", "default family"],
        "precedence_note": ("Model resolution in 999 runs through the native kie "
                            "skill's lookup (Row 3 MAP); this file carries the law "
                            "the lookup is judged by, not model data."),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 71 cross-repo parity checker (Item 27).")
    ap.add_argument("--onb-root", type=Path, required=True)
    ap.add_argument("--nine-root", type=Path, required=True)
    ap.add_argument("--json", type=Path, default=None, help="write the report as JSON")
    args = ap.parse_args(argv)

    onb_skill = args.onb_root / SKILL_ONB
    nine_skill = args.nine_root / SKILL_999
    allow_path = onb_skill / ALLOWLIST_REL
    if not onb_skill.is_dir() or not nine_skill.is_dir():
        print(f"FAIL: skill tree missing (onb: {onb_skill}, 999: {nine_skill})")
        return 2
    if not allow_path.is_file():
        print(f"FAIL: allowlist missing at {allow_path}")
        return 2
    allow = json.loads(allow_path.read_text(encoding="utf-8"))
    classes = allow.get("classes", {})

    failures, tracked, notes = [], [], []

    onb_files = {str(p.relative_to(onb_skill)): p
                 for p in sorted(onb_skill.rglob("*")) if p.is_file()
                 and "__pycache__" not in p.parts}
    nine_files = {str(p.relative_to(nine_skill)): p
                  for p in sorted(nine_skill.rglob("*")) if p.is_file()
                  and "__pycache__" not in p.parts}

    for rel, opath in onb_files.items():
        cls = classify(rel, classes)
        npath = nine_files.get(rel)
        if cls == "onb_only":
            if npath is not None:
                failures.append(f"onb_only file present in 999: {rel}")
            continue
        if cls == "nine_only" or cls == "generated":
            continue  # checked from the 999 side below
        if npath is None:
            if cls in ("adapter", "version", "changelog", "neutral"):
                failures.append(f"missing in 999 ({cls}): {rel}")
            continue
        ob, nb = opath.read_bytes(), npath.read_bytes()
        if cls == "neutral":
            if ob != nb:
                failures.append(f"byte drift in neutral file: {rel}")
        elif cls == "adapter":
            if ob != nb:
                added, removed = diff_counts(ob, nb)
                tracked.append({"file": rel, "class": "adapter",
                                "lines_added": added, "lines_removed": removed})
        elif cls == "version":
            om, nm = major_of(ob.decode("utf-8", "replace")), major_of(nb.decode("utf-8", "replace"))
            if om is None or nm is None or om != nm:
                failures.append(f"version major mismatch: {rel} (onb {om!r}, 999 {nm!r})")
            elif ob != nb:
                tracked.append({"file": rel, "class": "version",
                                "note": "per-repo version files; majors match"})
        elif cls == "changelog":
            if ob != nb:
                tracked.append({"file": rel, "class": "changelog",
                                "note": "per-repo changelog; bytes not compared"})

    nine_only_globs = classes.get("nine_only", {}).get("globs", [])
    for rel, npath in nine_files.items():
        if rel in onb_files:
            continue
        cls = classify(rel, classes)
        if cls == "nine_only" or cls == "generated":
            continue
        if any(fnmatch.fnmatch(rel, g) for g in nine_only_globs):
            continue
        failures.append(f"unclassified file present only in 999: {rel}")
    for g in nine_only_globs:
        if not any(fnmatch.fnmatch(rel, g) for rel in nine_files):
            failures.append(f"required 999-only file missing: {g}")

    # Generated policy data: recompute and compare payloads.
    gen_rel = "references/kie-policy-999.json"
    gate_path = onb_skill / "scripts" / "stage_gate.py"
    gen_path = nine_skill / gen_rel
    if not gen_path.is_file():
        failures.append(f"generated file missing in 999: {gen_rel}")
    elif gate_path.is_file():
        try:
            actual = json.loads(gen_path.read_text(encoding="utf-8"))
            expected = policy_payload(gate_path.read_text(encoding="utf-8"))
            payload_keys = set(expected)
            if {k: actual.get(k) for k in payload_keys} != expected:
                failures.append(f"generated payload drift: {gen_rel} "
                                f"(regenerate with the sync; do not hand-edit)")
            if "generated_by" not in actual:
                failures.append(f"generated file lacks its generation stamp: {gen_rel}")
        except ValueError as exc:
            failures.append(f"generated file unreadable: {gen_rel} ({exc})")

    # Tracked repo-level files.
    for entry in allow.get("tracked_repo_files", []):
        rel = entry["path"]
        a, b = args.onb_root / rel, args.nine_root / rel
        if not a.is_file():
            failures.append(f"tracked file missing in onboarding: {rel}")
        elif not b.is_file():
            failures.append(f"tracked file missing in 999: {rel}")
        elif a.read_bytes() != b.read_bytes():
            failures.append(f"tracked file drift: {rel}")

    # GHL pack, per its manifest.
    pack_path = onb_skill / PACK_MANIFEST_REL
    if not pack_path.is_file():
        failures.append(f"GHL pack manifest missing: {PACK_MANIFEST_REL}")
    else:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        for item in pack.get("files", []):
            dest = item["dest"]
            dpath = args.nine_root / dest
            if item.get("verdict") == "exclude":
                if dpath.is_file():
                    failures.append(f"excluded GHL pack file present in 999: {dest}")
                continue
            if not dpath.is_file():
                failures.append(f"GHL pack file missing in 999: {dest}")
                continue
            if item.get("class") == "neutral":
                spath = args.onb_root / item["source"]
                if not spath.is_file():
                    failures.append(f"GHL pack source missing in onboarding: {item['source']}")
                elif spath.read_bytes() != dpath.read_bytes():
                    failures.append(f"GHL pack neutral byte drift: {dest}")
            else:
                spath = args.onb_root / item["source"]
                if spath.is_file() and spath.read_bytes() != dpath.read_bytes():
                    added, removed = diff_counts(spath.read_bytes(), dpath.read_bytes())
                    tracked.append({"file": dest, "class": "ghl-pack-adapter",
                                    "seams": item.get("seams", []),
                                    "lines_added": added, "lines_removed": removed})
        notes.append(f"ghl_pack_version (onboarding manifest): {pack.get('ghl_pack_version')}")

    report = {"failures": failures, "tracked_differences": tracked, "notes": notes}
    for t in tracked:
        print(f"TRACKED {t.get('class')}: {t['file']} "
              f"{t.get('lines_added', '')} {t.get('lines_removed', '')} {t.get('note', '')}".rstrip())
    for n in notes:
        print(f"NOTE {n}")
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print(f"PARITY FAIL: {len(failures)} failure(s), {len(tracked)} tracked difference(s)")
    else:
        print(f"PARITY PASS: no unclassified drift; {len(tracked)} tracked difference(s) reported")
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
