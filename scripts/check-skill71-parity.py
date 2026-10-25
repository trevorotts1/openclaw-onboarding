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
               (the vendored enforcer, the frontmatter guard, and the
               shared registry/design dependencies the skill reads)
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
import tempfile
from pathlib import Path

SKILL_ONB = "71-blackceo-signature-page"
SKILL_999 = ".claude/skills/blackceo-signature-page"
ALLOWLIST_REL = "repo-integration/skill71-sync-allowlist.json"
PACK_MANIFEST_REL = "repo-integration/ghl-pack-manifest.json"

# Shared dependencies the skill reads across the tree boundary. Every one of
# them must be tracked so the two editions cannot drift apart unnoticed.
SHARED_TRACKED = (
    "shared-utils/signature_launch/domain/prompt-policy-registry.json",
    "shared-utils/signature_launch/design/design.css",
    "shared-utils/signature_launch/design/tokens/tokens.py",
)


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


def shipped_allowlist():
    """The allowlist in whichever of the two layouts this script lives in."""
    repo = Path(__file__).resolve().parents[1]
    for rel in (SKILL_ONB, SKILL_999):
        path = repo / rel / ALLOWLIST_REL
        if path.is_file():
            return path
    return None


def check_tracked_files(onb_root: Path, nine_root: Path, allow: dict):
    """Compare the repo-level files both trees carry — and prove 999 reaches them.

    The 999 skill resolves cross-tree assets BESIDE its own directory
    (`.claude/skills/shared-utils/...`), which that repo provides as a link to
    its root `shared-utils/`. Comparing repo-root copies alone would pass while
    the installed skill resolved nothing, so an entry marked
    `resolves_via_sibling` also requires that sibling path to resolve to the
    very copy compared here.

    A copy that resolves back to the onboarding file proves nothing either: a
    shared registry the 999 tree points at rather than carries certifies
    itself. That is a failure, never a pass.
    """
    failures, notes = [], []
    onb_res = onb_root.resolve()
    for entry in allow.get("tracked_repo_files", []):
        rel = entry["path"]
        a, b = onb_root / rel, nine_root / rel
        if not a.is_file():
            failures.append(f"tracked file missing in onboarding: {rel}")
            continue
        if not b.is_file():
            failures.append(f"tracked file missing in 999: {rel}")
            continue
        a_res, b_res = a.resolve(), b.resolve()
        if b_res == a_res or onb_res in b_res.parents:
            failures.append(
                f"tracked file self-certifies (999 resolves to the onboarding "
                f"file): {rel} -> {b_res}")
            continue
        if a.read_bytes() != b.read_bytes():
            failures.append(f"tracked file drift: {rel}")
            continue
        if entry.get("resolves_via_sibling"):
            sibling = (nine_root / SKILL_999).parent / rel
            if not sibling.is_file():
                failures.append(
                    f"tracked file unreachable from the 999 skill (sibling link "
                    f"missing): {rel} -> {sibling}")
            elif not sibling.samefile(b):
                # Present is not resolved: a sibling link that lands anywhere
                # but the compared 999 copy -- the onboarding file above all --
                # lets the skill read bytes parity never judged.
                failures.append(
                    f"tracked file sibling link does not reach the compared 999 "
                    f"copy (self-certifying or drifted): {rel} -> "
                    f"{sibling.resolve()}")
            else:
                notes.append(f"shared sibling resolves to the compared copy: {rel}")
    return failures, notes


def self_check() -> int:
    bad = []
    path = shipped_allowlist()
    if path is None:
        print("  [FAIL] shipped allowlist not found under either skill layout")
        print("SELF-CHECK FAIL")
        return 1
    allow = json.loads(path.read_text(encoding="utf-8"))
    entries = {e["path"]: e for e in allow.get("tracked_repo_files", [])}
    for rel in SHARED_TRACKED:
        entry = entries.get(rel)
        if entry is None:
            bad.append(f"shared dependency not tracked for parity: {rel}")
        elif not entry.get("resolves_via_sibling"):
            bad.append(f"shared dependency does not require sibling resolution: {rel}")
    subset = {"tracked_repo_files": [entries[r] for r in SHARED_TRACKED if r in entries]}

    def fixture(tmp: Path, nine_bytes=b"same", certifying=False, sibling=True,
                sibling_to_onb=False):
        onb, nine = tmp / "onb", tmp / "nine"
        for rel in SHARED_TRACKED:
            (onb / rel).parent.mkdir(parents=True, exist_ok=True)
            (onb / rel).write_bytes(b"same")
        for rel in SHARED_TRACKED:
            (nine / rel).parent.mkdir(parents=True, exist_ok=True)
            if certifying:
                (nine / rel).symlink_to(onb / rel)
            else:
                (nine / rel).write_bytes(nine_bytes)
        skills = (nine / SKILL_999).parent
        skills.mkdir(parents=True, exist_ok=True)
        if sibling_to_onb:
            (skills / "shared-utils").symlink_to(onb / "shared-utils")
        elif sibling:
            (skills / "shared-utils").symlink_to(Path("../../shared-utils"))
        return onb, nine

    cases = (
        (dict(), False, "matching copies through the sibling link"),
        (dict(nine_bytes=b"drift"), True, "byte drift"),
        (dict(certifying=True), True, "self-certifying link to the onboarding file"),
        (dict(sibling=False), True, "missing sibling link"),
        (dict(sibling_to_onb=True), True,
         "sibling link pointing at the onboarding tree"),
    )
    for kwargs, want_fail, label in cases:
        with tempfile.TemporaryDirectory() as td:
            onb, nine = fixture(Path(td), **kwargs)
            fails, _notes = check_tracked_files(onb, nine, subset)
        if bool(fails) != want_fail:
            bad.append(f"tracked {label}: want failure={want_fail}, got {fails}")
    with tempfile.TemporaryDirectory() as td:
        onb, nine = fixture(Path(td))
        (nine / SHARED_TRACKED[0]).unlink()
        fails, _notes = check_tracked_files(onb, nine, subset)
    if not any("missing in 999" in f for f in fails):
        bad.append(f"tracked file absent in 999 went unreported: {fails}")

    for line in bad:
        print(f"  [FAIL] {line}")
    if bad:
        print("SELF-CHECK FAIL")
        return 1
    total = len(SHARED_TRACKED) + len(cases) + 1
    print(f"SELF-CHECK PASS — {total} parity cases "
          f"({len(SHARED_TRACKED)} shared dependencies tracked, {len(cases)} "
          f"tracked-file comparisons, 1 absence)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 71 cross-repo parity checker (Item 27).")
    ap.add_argument("--onb-root", type=Path, default=None)
    ap.add_argument("--nine-root", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None, help="write the report as JSON")
    ap.add_argument("--self-check", action="store_true",
                    help="test the tracked-file comparison and exit")
    args = ap.parse_args(argv)
    if args.self_check:
        return self_check()
    if args.onb_root is None or args.nine_root is None:
        ap.error("--onb-root and --nine-root are required")

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

    # Tracked repo-level files, including the shared registry and design
    # dependencies the skill reads across the tree boundary.
    tracked_failures, tracked_notes = check_tracked_files(args.onb_root, args.nine_root, allow)
    failures += tracked_failures
    notes += tracked_notes

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
