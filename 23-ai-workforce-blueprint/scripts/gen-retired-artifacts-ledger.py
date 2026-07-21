#!/usr/bin/env python3
"""
gen-retired-artifacts-ledger.py — build templates/role-library/_retired.json,
the provenance ALLOWLIST that lets a box safely drop a canonical file the
library has DELETED.

────────────────────────────────────────────────────────────────────────────
THE DEFECT (measured 2026-07-21, 30 of 36 boxes)
────────────────────────────────────────────────────────────────────────────
Canonical deletions propagate to ONE tree and no others.

  WORKS — ~/.openclaw/skills/<NN-skill-name>/ is replaced WHOLESALE by the
  updater, so a deleted file is genuinely gone:

      update-skills.sh:2052-2063
          # Remove old version if exists
          rm -rf "$SKILLS_DIR/$SKILL_NAME"
          ...
          cp -r "${SKILL_DIR%/}" "$SKILLS_DIR/"

      Measured: role-library = 913 files, ZERO orphans, on all 30 reachable
      boxes. DO NOT "FIX" THIS PATH.

  BROKEN — the PERSISTENT staging checkout is merge-copied and never pruned:

      install.sh:3165
          cp -r "$TEMP_EXTRACT/openclaw-onboarding-main/"* "$ONBOARDING_DIR/"

      $ONBOARDING_DIR is $OC_CONFIG/onboarding (install.sh:2581) — a durable
      directory that also holds client state, so it is never wiped. Every file
      canonical has ever deleted is still in it. Measured on one box:
      onboarding/.../graphics/sops = 43 files vs the live tree's 36.

  BROKEN — install.sh then installs skills FROM that dirty staging tree, and
  its own copy is additive too (no rm -rf of the destination):

      install.sh:3193-3205
          mkdir -p "$SKILLS_DIR/$SKILL_NAME"
          for ITEM in "$SKILL_DIR"/*; do
              ...
                      if [ -d "$ITEM" ]; then
                          cp -r "$ITEM" "$SKILLS_DIR/$SKILL_NAME/"

      So re-running install.sh can RE-SEED retired files into the live,
      agent-readable skill tree.

  BROKEN — stray copies inside the skill search path that the updater's
  wholesale replace never visits because they are not `<NN-skill-name>`
  directories: skills/onboarding/, skills/openclaw-onboarding/,
  skills/templates/role-library/. Measured on one box:
  ~/.openclaw/skills/onboarding/.../chief-design-officer-sops.md — 17,221 B,
  dated Jun 22 — the SUPERSEDED predecessor of a file enhanced to 22,496 B in
  the same commit that deleted it, sitting in the path agents read.

Measured scale: 755 orphan instances across 30 boxes; 369 in agent-reachable
trees, 207 of those MISLEADING (superseded content still readable); 0 in the
live canonical dir. 24 distinct deleted files from 4 commits (f5942a68,
1cc78bd6, d47d2fd2, 34e4b6a3) across 9 departments.

────────────────────────────────────────────────────────────────────────────
WHY A LEDGER (AND NOT rsync --delete / "anything not in the manifest")
────────────────────────────────────────────────────────────────────────────
The reconcile that removes those files runs on CLIENT MACHINES. The bar is
that it must be IMPOSSIBLE for it to delete something a client authored.
"Delete anything not in _index.json" is a BLACKLIST-shaped rule: a
client-authored file is also not in _index.json, so that rule eats client work.

This ledger is the ALLOWLIST. Per retired artifact it records:
  - lib_path — the path RELATIVE TO templates/role-library's parent, i.e.
    "templates/role-library/<dept>/sops/<file>.md" (5+ components), and
  - content_shas — EVERY content_sha that path carried in canonical history.

reconcile-orphan-library-files.py may quarantine a box file only when BOTH
keys match: the file's path ENDS WITH a ledger lib_path AND its content_sha is
one this ledger records. A client-authored file fails the path key. A
client-EDITED dead canonical file fails the sha key and is reported as a
CONFLICT, never removed.

A useful structural consequence of anchoring on "templates/role-library/…":
the reconcile can never reach a client's MATERIALIZED workforce
(<workspace>/departments/<dept>/…), because those paths do not contain
"templates/role-library/". The tree holding each role's client-written
IDENTITY.md / SOUL.md / MEMORY.md / HEARTBEAT.md is out of reach BY
CONSTRUCTION, not by a rule someone could get wrong later.

content_sha is computed with hash-content-manifest.py's own
normalize_canonical() — the SAME normalization _index.json is stamped with —
so a re-stamped provenance marker or **Last updated:** header still matches
while any real content edit does not.

────────────────────────────────────────────────────────────────────────────
SCOPE
────────────────────────────────────────────────────────────────────────────
Tracked tree: 23-ai-workforce-blueprint/templates/role-library/**.md

That is the whole measured defect surface (all 24 files, all 9 departments)
and the only content on these boxes that an AGENT READS AS INSTRUCTIONS. The
repo has ~3,993 retired paths in total, but 3,042 of those are generated
graphify-out artifacts and most of the rest are pre-rename skill directories
that no agent reads; widening the ledger to them would add risk without
addressing a measured read hazard. Extending the tracked tree later is a
one-constant change (TRACKED_TREES).

Each entry is tagged kind = "sop" | "role" for reporting. BOTH kinds are
actionable here — inside templates/role-library/ every file is a canonical
TEMPLATE, not a materialized role folder, so removing a dead template destroys
no client state.

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  (no args)     regenerate <skill>/templates/role-library/_retired.json
  --check       recompute in memory and DIFF against the on-disk ledger.
                Exit 0 = in sync, 6 = drift. This is the CI gate that keeps
                the fix from rotting: delete a library file and CI fails until
                the ledger records it, so the boxes can act on it.
  --repo <dir>  repo root (default: `git rev-parse --show-toplevel`)
  --out  <path> ledger path override
  --json        print the computed ledger to stdout instead of writing

EXIT CODES
  0  wrote / verified in sync
  1  usage error
  2  git unavailable, not a repo, or the tracked tree does not exist
  6  --check drift (regenerate the ledger)
"""
import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT = Path(__file__).resolve()
SKILL_DIR = _SCRIPT.parent.parent
SCRIPTS = SKILL_DIR / "scripts"

# Tracked trees, RELATIVE TO THE REPO ROOT. Widening the ledger is a change
# here plus a regeneration — nothing in the reconcile tool needs to know.
TRACKED_TREES = ("23-ai-workforce-blueprint/templates/role-library",)

# The anchor a box path is matched against. Everything under a tracked tree is
# recorded as "<ANCHOR_FROM>/<rest>", e.g.
#   templates/role-library/graphics/sops/chief-design-officer-sops.md
# so the SAME entry matches every place the library is copied on a box:
#   skills/23-ai-workforce-blueprint/templates/role-library/...
#   onboarding/23-ai-workforce-blueprint/templates/role-library/...
#   skills/onboarding/23-ai-workforce-blueprint/templates/role-library/...
#   skills/templates/role-library/...
ANCHOR_FROM = "templates/"

SCHEMA = "openclaw/retired-artifacts@2"


def _load_hasher():
    """Reuse hash-content-manifest.py's normalization — one algorithm, one file."""
    src = SCRIPTS / "hash-content-manifest.py"
    if not src.is_file():
        print(f"FATAL: hash-content-manifest.py not found at {src}", file=sys.stderr)
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("_hcm", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo, *args, allow_fail=False):
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    except FileNotFoundError:
        print("FATAL: git is not available", file=sys.stderr)
        sys.exit(2)
    if out.returncode != 0:
        if allow_fail:
            return None
        print(f"FATAL: git {' '.join(args[:3])} failed: "
              f"{out.stderr.decode('utf-8', 'replace').strip()}", file=sys.stderr)
        sys.exit(2)
    return out.stdout.decode("utf-8", "replace")


def _resolve_repo(explicit):
    if explicit:
        return Path(explicit).resolve()
    top = _git(SKILL_DIR, "rev-parse", "--show-toplevel", allow_fail=True)
    if not top:
        print("FATAL: not inside a git repo (pass --repo)", file=sys.stderr)
        sys.exit(2)
    return Path(top.strip()).resolve()


def _anchor(repo_path):
    """'23-.../templates/role-library/x/y.md' -> 'templates/role-library/x/y.md'."""
    idx = repo_path.find("/" + ANCHOR_FROM)
    if idx < 0:
        return None
    return repo_path[idx + 1:]


def compute_ledger(repo, hcm):
    head = (_git(repo, "rev-parse", "HEAD") or "").strip()

    present, ever = set(), set()
    for tree in TRACKED_TREES:
        for line in (_git(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", tree) or "").split("\n"):
            line = line.strip()
            if line:
                present.add(line)
        # Every path this tree has EVER carried. --no-renames so a rename is
        # delete(old)+add(new): from a box's point of view the OLD name is
        # retired and must be reconcilable. Deriving "retired" as
        # (ever - present) rather than from --diff-filter=D also catches paths
        # whose deletion landed in a MERGE commit, which `git log` omits by
        # default (that is how the 8th retired SOP,
        # presentations/sops/deck-discovery-strategist-sops.md, is found).
        log = _git(repo, "log", "--no-renames", "--pretty=format:",
                   "--name-only", "--diff-filter=ACDMRT", "--", tree) or ""
        for line in log.split("\n"):
            line = line.strip()
            if line.startswith(tree + "/") and line.endswith(".md"):
                ever.add(line)

    artifacts = []
    for rel in sorted(ever - present):
        lib_path = _anchor(rel)
        if not lib_path:
            continue
        # lib_path == "templates/role-library/<dept>/[sops/]<file>.md"
        tail = lib_path.split("/")[2:]
        dept = tail[0] if tail else ""
        kind = "sop" if (len(tail) == 3 and tail[1] == "sops") else "role"
        commit, when = _deletion_record(repo, rel)
        artifacts.append({
            "lib_path": lib_path,
            "repo_path": rel,
            "dept": dept,
            "file": lib_path.rsplit("/", 1)[-1],
            "kind": kind,
            "content_shas": _shas_for_path(repo, rel, hcm),
            "retired_in": commit,
            "retired_at": when,
        })

    artifacts.sort(key=lambda e: e["lib_path"])
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_ref": head,
        "tracked_trees": list(TRACKED_TREES),
        "algo": {"content_sha": "sha256 over hash-content-manifest.py normalize_canonical()"},
        "counts": {
            "artifacts": len(artifacts),
            "sops": sum(1 for a in artifacts if a["kind"] == "sop"),
            "roles": sum(1 for a in artifacts if a["kind"] == "role"),
            "departments": len({a["dept"] for a in artifacts}),
        },
        "artifacts": artifacts,
    }


def _shas_for_path(repo, rel, hcm):
    """Every content_sha this path ever carried, oldest commit first."""
    shas, seen = [], set()
    commits = [c.strip() for c in
               (_git(repo, "log", "--no-renames", "--pretty=%H", "--", rel) or "").split("\n")
               if c.strip()]
    for commit in reversed(commits):
        blob = _git(repo, "cat-file", "-p", f"{commit}:{rel}", allow_fail=True)
        if blob is None:
            continue                      # path absent at this commit (the delete)
        sha = hcm.content_sha_of_text(blob)
        if sha not in seen:
            seen.add(sha)
            shas.append(sha)
    return shas


def _deletion_record(repo, rel):
    out = _git(repo, "log", "--no-renames", "--diff-filter=D", "-1",
               "--pretty=%H%x09%cI", "--", rel, allow_fail=True)
    if not out or "\t" not in out:
        return (None, None)
    commit, _, when = out.strip().partition("\t")
    return (commit.strip(), when.strip())


def _comparable(led):
    """Drop the non-deterministic header fields so --check compares CONTENT."""
    return {
        "schema": led.get("schema"),
        "tracked_trees": led.get("tracked_trees"),
        "algo": led.get("algo"),
        "counts": led.get("counts"),
        "artifacts": led.get("artifacts"),
    }


def main():
    ap = argparse.ArgumentParser(description="Generate/verify the retired-artifacts ledger.")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    repo = _resolve_repo(args.repo)
    for tree in TRACKED_TREES:
        if not (repo / tree).is_dir():
            print(f"FATAL: tracked tree missing: {repo / tree}", file=sys.stderr)
            return 2

    hcm = _load_hasher()
    ledger = compute_ledger(repo, hcm)
    out_path = Path(args.out) if args.out else \
        (repo / TRACKED_TREES[0] / "_retired.json")

    if args.json:
        print(json.dumps(ledger, indent=2))
        return 0

    if args.check:
        if not out_path.is_file():
            print(f"DRIFT: ledger missing: {out_path}", file=sys.stderr)
            print("  -> run: python3 23-ai-workforce-blueprint/scripts/"
                  "gen-retired-artifacts-ledger.py", file=sys.stderr)
            return 6
        try:
            on_disk = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"DRIFT: ledger unreadable ({e})", file=sys.stderr)
            return 6
        if _comparable(on_disk) != _comparable(ledger):
            disk = {a.get("lib_path") for a in on_disk.get("artifacts", [])}
            new = {a.get("lib_path") for a in ledger.get("artifacts", [])}
            print("DRIFT: _retired.json does not match git history.", file=sys.stderr)
            for k in sorted(new - disk):
                print(f"  MISSING from ledger (canonical deleted it): {k}", file=sys.stderr)
            for k in sorted(disk - new):
                print(f"  STALE in ledger (path is live again): {k}", file=sys.stderr)
            if new == disk:
                print("  (same paths — a recorded content_sha set or a field changed)",
                      file=sys.stderr)
            print("  -> run: python3 23-ai-workforce-blueprint/scripts/"
                  "gen-retired-artifacts-ledger.py", file=sys.stderr)
            return 6
        c = ledger["counts"]
        print(f"OK: _retired.json in sync with git history "
              f"(artifacts={c['artifacts']} sops={c['sops']} roles={c['roles']} "
              f"departments={c['departments']})")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    c = ledger["counts"]
    print(f"wrote {out_path}")
    print(f"  retired artifacts : {c['artifacts']} "
          f"(sops={c['sops']} roles={c['roles']}) across {c['departments']} departments")
    return 0


if __name__ == "__main__":
    sys.exit(main())
