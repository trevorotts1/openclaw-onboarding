#!/usr/bin/env python3
"""
check-duplicate-sop-drift.py — DUPLICATE-SOP AUTHORITY GATE (FIX-DELIVERY-05).

────────────────────────────────────────────────────────────────────────────
THE DEFECT
────────────────────────────────────────────────────────────────────────────
The same SOP filename ships from TWO trees with DIFFERENT content:

  A. 23-ai-workforce-blueprint/templates/role-library/<dept>/sops/
  B. universal-sops/<pack>/

Both land on every client box (install.sh L3674-3676 and update-skills.sh
L5139-5141 copy the whole universal-sops tree to $SKILLS_DIR/universal-sops;
the role-library tree is materialized into the department by
scaffold_department / refresh-dept-scripts). Nothing anywhere compares the two.

Measured on this repo at the time this gate was written: 8 duplicated
basenames, 8 of which DISAGREE, 0 of which agree — across all 7 role-library
departments that ship a sops/ dir. Every one is in `presentations`.

WHY IT MATTERS EVEN THOUGH NO COPIER OVERWRITES THE OTHER
─────────────────────────────────────────────────────────
None of the 8 appear in PIPELINE-MANIFEST.json's `sop_refs` (all 29 refs
resolve to role-library-only filenames), so the ENGINE is not reading the
universal-sops copies. The harm is to AGENTS: role .md files cite the
universal-sops path by name — e.g.
role-library/presentations/slide-image-creator.md line 172 cites
`universal-sops/presentation-image-library/...` — so an agent that follows a
citation reads one document while the department's own sops/ dir holds a
materially different one. Today the universal-sops copies of all four SOP-IMG
files are still stamped "**Status:** DRAFT for overhaul" while the
role-library copies are the overhauled "**Status:** Reference SOP" (SOP-IMG-01:
276 lines vs 214, including a whole mandatory section 1A that exists in only
one copy). That is two doctrines under one filename.

────────────────────────────────────────────────────────────────────────────
DECLARED AUTHORITY (evidence, not preference — see duplicate-sop-authority.json)
────────────────────────────────────────────────────────────────────────────
The authority is per-ARTIFACT, not per-directory, because the repo genuinely
uses both directions:

  PIPELINE-MANIFEST.json + MASTER-QC-AUTOFAIL-RULESET.md
      -> universal-sops/presentation-slide-craft/ IS canonical.
         Proof: _u001_presentations_manifest_placement in BOTH installers
         (update-skills.sh L5340-5341, install.sh L7528-7529) reads
         _manifest_src/_ruleset_src from $SKILLS_DIR/universal-sops/
         presentation-slide-craft/ and copies them INTO the department's sops/,
         then writes MANIFEST-SOURCE.txt recording source_path= that path.
         sync_check.py L130 says the same in prose: "install.sh u001 placement
         (which materializes FROM the cluster copy)".

  the 8 duplicated SOP .md files
      -> role-library/presentations/sops/ IS canonical.
         Proof: U001 copies ONLY those two files from universal-sops — it never
         copies a SOP-SLIDE-*/SOP-IMG-* .md. The only tree that reaches a
         materialized department's sops/*.md is the role-library. Corroborated
         by content: the role-library copies are the overhauled "Reference SOP"
         versions, the universal-sops copies are the pre-overhaul "DRAFT for
         overhaul" versions.

This gate does NOT rewrite SOP content — doctrine is the operator's. It makes
the disagreement impossible to EXTEND silently.

────────────────────────────────────────────────────────────────────────────
HOW THE GATE CANNOT BE OUTRUN (content-pinned waivers)
────────────────────────────────────────────────────────────────────────────
A waiver does NOT say "this filename may disagree". It pins the sha256 of
BOTH copies. The 8 known disagreements are tolerated at EXACTLY their current
bytes. Edit either copy — either side, one character — and its sha no longer
matches the pinned pair, the waiver stops applying, and the gate FAILS. A new
duplicated filename that disagrees has no waiver at all and fails immediately.

So the existing backlog is recorded rather than silently rewritten (Trevor's
doctrine stays Trevor's), while NEW drift is impossible to land unnoticed.

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  --check      (default) scan + compare + apply waivers. exit 0 clean, 1 drift.
  --json       machine-readable report on stdout.
  --record     REGENERATE duplicate-sop-authority.json waivers from the current
               on-disk state. An explicit operator action — never run by CI.
               Use after deliberately reconciling or deliberately changing a
               copy, so the new bytes become the pinned baseline.
  --repo-root  override the repo root (default: walk up from this file).

EXIT CODES
  0  no duplicated SOP filename disagrees, except pairs whose BOTH shas match
     a recorded waiver.
  1  at least one duplicated SOP filename disagrees without a matching waiver,
     OR a recorded waiver no longer matches the bytes on disk (stale waiver).
  2  the gate could not run (repo layout not found, registry unreadable).
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_NAME = "duplicate-sop-authority.json"


def find_repo_root(start: Path):
    cur = start.resolve()
    for _ in range(12):
        if (cur / "universal-sops").is_dir() and \
           (cur / "23-ai-workforce-blueprint" / "templates" / "role-library").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_pairs(repo_root: Path):
    """Every (dept, role_library_copy, universal_sops_copy) sharing a basename.

    Deterministic: both sides sorted. A basename appearing more than once under
    universal-sops yields one pair per occurrence (none do today, but the gate
    must not silently pick one).
    """
    rl = repo_root / "23-ai-workforce-blueprint" / "templates" / "role-library"
    us = repo_root / "universal-sops"
    universal = {}
    for p in sorted(us.rglob("*.md")):
        if p.is_file():
            universal.setdefault(p.name, []).append(p)
    pairs = []
    for dept in sorted(rl.iterdir()):
        sops = dept / "sops"
        if not sops.is_dir():
            continue
        for p in sorted(sops.rglob("*.md")):
            for q in universal.get(p.name, []):
                pairs.append((dept.name, p, q))
    return pairs


def load_registry(repo_root: Path):
    path = repo_root / "scripts" / REGISTRY_NAME
    if not path.is_file():
        return {"waivers": []}, path
    try:
        return json.loads(path.read_text()), path
    except (OSError, ValueError) as e:
        print(f"FATAL: could not read {path}: {e}", file=sys.stderr)
        sys.exit(2)


def evaluate(repo_root: Path):
    pairs = collect_pairs(repo_root)
    registry, reg_path = load_registry(repo_root)
    # index waivers by (relative role-lib path, relative universal path)
    waivers = {}
    for w in registry.get("waivers", []):
        waivers[(w["role_library_path"], w["universal_sops_path"])] = w

    agree, waived, violations, stale = [], [], [], []
    seen_keys = set()
    for dept, rlp, usp in pairs:
        rel_r = str(rlp.relative_to(repo_root))
        rel_u = str(usp.relative_to(repo_root))
        sr, su = sha256_of(rlp), sha256_of(usp)
        key = (rel_r, rel_u)
        seen_keys.add(key)
        if sr == su:
            agree.append({"dept": dept, "file": rlp.name,
                          "role_library_path": rel_r, "universal_sops_path": rel_u})
            continue
        w = waivers.get(key)
        if w and w.get("role_library_sha256") == sr and w.get("universal_sops_sha256") == su:
            waived.append({"dept": dept, "file": rlp.name,
                           "role_library_path": rel_r, "universal_sops_path": rel_u,
                           "reason": w.get("reason", "")})
        elif w:
            stale.append({
                "dept": dept, "file": rlp.name,
                "role_library_path": rel_r, "universal_sops_path": rel_u,
                "pinned_role_library_sha256": w.get("role_library_sha256"),
                "actual_role_library_sha256": sr,
                "pinned_universal_sops_sha256": w.get("universal_sops_sha256"),
                "actual_universal_sops_sha256": su,
                "changed_side": ("role-library" if w.get("role_library_sha256") != sr else "")
                                + ("+" if (w.get("role_library_sha256") != sr and
                                           w.get("universal_sops_sha256") != su) else "")
                                + ("universal-sops" if w.get("universal_sops_sha256") != su else ""),
            })
        else:
            violations.append({"dept": dept, "file": rlp.name,
                               "role_library_path": rel_r, "universal_sops_path": rel_u,
                               "role_library_sha256": sr, "universal_sops_sha256": su})

    orphan_waivers = [{"role_library_path": k[0], "universal_sops_path": k[1]}
                      for k in waivers if k not in seen_keys]
    return {
        "pairs_examined": len(pairs),
        "agree": agree,
        "waived": waived,
        "violations": violations,
        "stale_waivers": stale,
        "orphan_waivers": orphan_waivers,
        "registry_path": str(reg_path),
        "canonical_source": registry.get("canonical_source", {}),
    }


def do_record(repo_root: Path):
    pairs = collect_pairs(repo_root)
    registry, reg_path = load_registry(repo_root)
    prev = {(w["role_library_path"], w["universal_sops_path"]): w
            for w in registry.get("waivers", [])}
    waivers = []
    for dept, rlp, usp in pairs:
        sr, su = sha256_of(rlp), sha256_of(usp)
        if sr == su:
            continue
        rel_r = str(rlp.relative_to(repo_root))
        rel_u = str(usp.relative_to(repo_root))
        old = prev.get((rel_r, rel_u), {})
        waivers.append({
            "file": rlp.name,
            "dept": dept,
            "role_library_path": rel_r,
            "universal_sops_path": rel_u,
            "role_library_sha256": sr,
            "universal_sops_sha256": su,
            "canonical_side": old.get("canonical_side", "role-library"),
            "reason": old.get("reason",
                              "Pre-existing divergence recorded, not reconciled. Content is "
                              "doctrine and belongs to the operator. Pinned by sha256 on BOTH "
                              "sides: any edit to either copy invalidates this waiver and the "
                              "gate fails until the change is reviewed and re-recorded."),
            "recorded_at": old.get("recorded_at",
                                   datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        })
    registry["waivers"] = waivers
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(f"recorded {len(waivers)} waiver(s) to {reg_path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail when two copies of the same SOP filename disagree.")
    ap.add_argument("--check", action="store_true", default=True)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--repo-root", default=None)
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root) if args.repo_root else find_repo_root(Path(__file__).parent)
    if repo_root is None:
        print("FATAL: repo root not found (need universal-sops/ + "
              "23-ai-workforce-blueprint/templates/role-library/)", file=sys.stderr)
        return 2

    if args.record:
        return do_record(repo_root)

    r = evaluate(repo_root)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print("== DUPLICATE-SOP AUTHORITY GATE ==")
        print(f"   duplicated basenames examined : {r['pairs_examined']}")
        print(f"   identical (no drift)          : {len(r['agree'])}")
        print(f"   disagree, waived at pinned sha: {len(r['waived'])}")
        print(f"   disagree, NOT waived          : {len(r['violations'])}")
        print(f"   waivers stale (bytes moved)   : {len(r['stale_waivers'])}")
        print(f"   waivers for vanished pairs    : {len(r['orphan_waivers'])}")
        for v in r["violations"]:
            print(f"\n   DRIFT (unwaived): {v['file']}  [{v['dept']}]", file=sys.stderr)
            print(f"     role-library : {v['role_library_path']}  sha {v['role_library_sha256'][:16]}", file=sys.stderr)
            print(f"     universal    : {v['universal_sops_path']}  sha {v['universal_sops_sha256'][:16]}", file=sys.stderr)
        for s in r["stale_waivers"]:
            print(f"\n   STALE WAIVER: {s['file']}  [{s['dept']}] — {s['changed_side']} copy changed "
                  f"since the waiver was recorded.", file=sys.stderr)
            print(f"     role-library pinned {str(s['pinned_role_library_sha256'])[:16]} "
                  f"actual {s['actual_role_library_sha256'][:16]}", file=sys.stderr)
            print(f"     universal    pinned {str(s['pinned_universal_sops_sha256'])[:16]} "
                  f"actual {s['actual_universal_sops_sha256'][:16]}", file=sys.stderr)

    if r["violations"] or r["stale_waivers"]:
        print("\nGATE FAILED: a duplicated SOP filename disagrees without a current waiver.\n"
              "  The two copies are BOTH delivered to every client box, so an agent gets\n"
              "  different doctrine depending on which path it follows.\n"
              "  Fix by making the non-canonical copy follow the canonical one (see\n"
              f"  canonical_source in {r['registry_path']}), or — if the divergence is\n"
              "  deliberate — re-record the baseline with:\n"
              "      python3 scripts/check-duplicate-sop-drift.py --record",
              file=sys.stderr)
        return 1
    print("\nGATE PASSED: no unwaived duplicate-SOP disagreement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
