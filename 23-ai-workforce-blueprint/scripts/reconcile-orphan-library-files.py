#!/usr/bin/env python3
"""
reconcile-orphan-library-files.py — make canonical DELETIONS reach the trees
the updater's wholesale replace never touches, without it ever being possible
to delete client-authored content.

────────────────────────────────────────────────────────────────────────────
WHAT IS BROKEN, AND WHAT IS NOT (measured 2026-07-21, 30 of 36 boxes)
────────────────────────────────────────────────────────────────────────────
ALREADY CORRECT — LEAVE ALONE.  ~/.openclaw/skills/<NN-skill-name>/ is
replaced WHOLESALE on every update, so a deleted canonical file really is gone
(update-skills.sh:2052-2063: `rm -rf "$SKILLS_DIR/$SKILL_NAME"` then
`cp -r "${SKILL_DIR%/}" "$SKILLS_DIR/"`). Measured: role-library = 913 files,
ZERO orphans, on all 30 reachable boxes. This tool changes nothing there — it
simply finds nothing to do, which is the correct result.

BROKEN #1 — the PERSISTENT staging checkout, install.sh:3165
    cp -r "$TEMP_EXTRACT/openclaw-onboarding-main/"* "$ONBOARDING_DIR/"
  merge-copied into $OC_CONFIG/onboarding (install.sh:2581), a durable
  directory that also holds client state and is therefore never wiped. Every
  file canonical has ever deleted is still in it (one box: .../graphics/sops =
  43 files vs the live tree's 36).

BROKEN #2 — install.sh installs skills FROM that dirty staging tree and its
  own copy is additive as well (install.sh:3193-3205: `mkdir -p
  "$SKILLS_DIR/$SKILL_NAME"` then per-item `cp -r`/`cp`, no rm -rf), so
  re-running install.sh can RE-SEED retired files into the live skill tree.

BROKEN #3 — strays inside the skill search path that the wholesale replace
  never visits because they are not `<NN-skill-name>` directories:
  skills/onboarding/, skills/openclaw-onboarding/, skills/templates/role-library/.
  One box carries ~/.openclaw/skills/onboarding/.../chief-design-officer-sops.md
  — 17,221 B, dated Jun 22 — the SUPERSEDED predecessor of a file enhanced to
  22,496 B in the very commit that deleted it, sitting where agents read.

Scale: 755 orphan instances across 30 boxes; 369 in agent-reachable trees, 207
of those MISLEADING; 0 in the live canonical dir.

────────────────────────────────────────────────────────────────────────────
THE SAFETY MODEL — ALLOWLIST, NEVER BLACKLIST
────────────────────────────────────────────────────────────────────────────
This tool deletes files on CLIENT MACHINES, so the rule is not "remove what is
not canonical" — a client-authored file is also not canonical, and that rule
would eat client work. This tool never enumerates a directory and decides what
to keep. It LOOKS FOR a closed list of known-dead files and ignores everything
else. A file is quarantined only when ALL of these hold:

  (a) it is inside a scan ROOT that is canonical-managed
      (<oc-root>/skills, <oc-root>/onboarding) and no path component is in the
      cold-backup / VCS / cache deny-list;
  (b) its path ENDS WITH a `lib_path` recorded in templates/role-library/
      _retired.json — i.e. "templates/role-library/<dept>/…/<file>.md", 5+
      path components — proving canonical once shipped exactly this file at
      exactly this place. The ledger is generated from git history by
      gen-retired-artifacts-ledger.py and CI-gated against drift;
  (c) its content_sha is one of the shas that path carried in canonical
      history (hash-content-manifest.py's normalize_canonical, the same
      normalization _index.json is stamped with, so a re-stamped provenance or
      **Last updated:** header still matches while a real edit does not);
  (d) the path is ABSENT from the live manifest _index.json (cross-checked;
      a ledger/manifest contradiction is fatal, see below).

Everything else is KEPT, by construction:
  ORPHAN     — (a)+(b)+(c)+(d)          -> quarantine, only with --apply
  CONFLICT   — retired path, bytes locally MODIFIED
                                        -> keep, reported LOUDLY, rc 4
  UNREADABLE — unreadable / undecodable / a symlink / resolves outside its
               root — genuinely UNDECIDABLE
                                        -> keep, reported LOUDLY, rc 4
  everything not matching a ledger path -> never examined at all

"I don't know what this is" always means KEEP.

TWO THINGS THIS TOOL STRUCTURALLY CANNOT REACH — not by a rule, by shape:
  1. A client's MATERIALIZED workforce, <workspace>/departments/<dept>/…,
     where each role's client-written IDENTITY.md / SOUL.md / MEMORY.md /
     HEARTBEAT.md live. Those paths do not contain "templates/role-library/",
     so no ledger entry can ever match one.
  2. COLD BACKUPS (skills.bak*, skills-backup-*, backups/, openclaw-backups/,
     master-files/, updater-src-*, *.bak*). They are rollback material with
     zero read risk; deleting them would be the bug. They are pruned from the
     walk before any file in them is looked at.

────────────────────────────────────────────────────────────────────────────
OTHER NON-NEGOTIABLES
────────────────────────────────────────────────────────────────────────────
DRY-RUN IS THE DEFAULT.  Without --apply no file is moved; the tool reports
  exactly what it WOULD quarantine. (It does write a receipt JSON — a report,
  not a mutation.)
BACK UP, NEVER UNLINK.  --apply MOVES each orphan under
  <oc-root>/.orphan-quarantine/<UTC-timestamp>/ with a manifest.json recording
  every original path + sha. `--restore <batch>` puts them back; the test
  suite proves the round trip.
FAIL LOUDLY.  A missing/corrupt manifest or ledger is rc 2 and NOTHING is
  touched. A conflict/unreadable file is rc 4. A failed move is rc 5. This
  tool never prints a success line while having skipped the work.
IDEMPOTENT.  A second run finds nothing (the files have moved) and is a no-op.
LAGGING BOXES.  Nothing here depends on the box being current: the ledger
  carries EVERY sha each retired path ever had, so a box many versions behind
  is reconciled just as precisely as a current one.

────────────────────────────────────────────────────────────────────────────
CLI
────────────────────────────────────────────────────────────────────────────
  --root <dir>        scan root (repeatable). Default: <oc-root>/skills and
                       <oc-root>/onboarding, where <oc-root> is
                       /data/.openclaw when present else ~/.openclaw
  --apply             actually quarantine. WITHOUT THIS THE TOOL IS DRY-RUN.
  --restore <dir>     restore a quarantine batch directory and exit
  --quarantine-root <dir>   where batches are written (default <oc-root>)
  --manifest <path>   override _index.json
  --ledger <path>     override _retired.json
  --json              machine-readable report on stdout

EXIT CODES
  0   clean — nothing actionable, or --apply completed with no conflicts
  10  DRY-RUN: orphans found that --apply would quarantine (same "actionable
      drift" convention as detect-stale-artifacts.py rc 10)
  4   at least one CONFLICT / UNREADABLE file — reported and SKIPPED, never
      removed
  5   --apply: a quarantine move failed
  2   fatal: manifest / ledger unusable — NOTHING was touched
  1   usage error
  (precedence: 2 > 5 > 4 > 10 > 0)
"""
import argparse
import fnmatch
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOL = "reconcile-orphan-library-files.py"
LEDGER_SCHEMA = "openclaw/retired-artifacts@2"
QUARANTINE_SCHEMA = "openclaw/orphan-quarantine@1"

# Directory-component deny-list. Matched with fnmatch against EVERY component
# of every path, and used to prune os.walk before descending. Cold backups are
# rollback material: removing them is a bug, not a feature.
DENY_COMPONENTS = (
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".orphan-quarantine", ".Trash", ".cache",
    "backups", "openclaw-backups", "master-files", "backup",
    "*.bak", "*.bak-*", "*.bak.*", "*.backup", "*.old",
    "skills.bak*", "skills-backup-*", "*-backup-*", "*-backup",
    "updater-src-*", "*-archive", "departments-archive",
    ".update-backup*", "*.orig", "*.rej",
)

# ── Self-locating skill-23 resolution (same pattern as floor-fill-driver.py) ──
_SCRIPT = Path(__file__).resolve()
_DEFAULT_SKILL_DIR = _SCRIPT.parent.parent


def _resolve_skill_dir():
    cands = []
    env = os.environ.get("OPENCLAW_SKILL23_DIR")
    if env:
        cands.append(Path(env))
    cands.append(_DEFAULT_SKILL_DIR)
    cands.append(Path.home() / ".openclaw/skills/23-ai-workforce-blueprint")
    cands.append(Path("/data/.openclaw/skills/23-ai-workforce-blueprint"))
    for c in cands:
        try:
            if (c / "templates" / "role-library" / "_index.json").is_file():
                return c
        except OSError:
            continue
    return _DEFAULT_SKILL_DIR


SKILL_DIR = _resolve_skill_dir()
LIBRARY = SKILL_DIR / "templates" / "role-library"


def oc_root():
    return Path("/data/.openclaw") if Path("/data/.openclaw").is_dir() \
        else (Path.home() / ".openclaw")


def _load_hasher():
    """content_sha must be computed by the SAME code that stamps _index.json."""
    src = SKILL_DIR / "scripts" / "hash-content-manifest.py"
    if not src.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_hcm_reconcile", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod if hasattr(mod, "content_sha_of_text") else None


def denied(component):
    return any(fnmatch.fnmatch(component, pat) for pat in DENY_COMPONENTS)


# ─── LOADERS (every failure here is FATAL — rc 2, nothing touched) ─────────────

def load_live_lib_paths(path):
    """-> (set of live 'templates/role-library/...' paths, None) or (None, reason)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, f"cannot read manifest {path}: {e}"
    live = set()
    for key in ("roles", "sops", "personas"):
        for entry in data.get(key) or []:
            if isinstance(entry, dict) and entry.get("path"):
                live.add(str(entry["path"]))
    if not live:
        return None, (f"manifest {path} lists no artifact paths — refusing to run "
                      f"(an empty manifest disables the live-vs-retired cross-check)")
    return live, None


def load_ledger(path):
    """-> ({lib_path: entry}, None) or (None, reason)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, f"cannot read retired-artifacts ledger {path}: {e}"
    if data.get("schema") != LEDGER_SCHEMA:
        return None, (f"ledger {path} has schema {data.get('schema')!r}, "
                      f"expected {LEDGER_SCHEMA!r}")
    out = {}
    for e in data.get("artifacts") or []:
        if not isinstance(e, dict):
            return None, f"ledger {path} has a malformed artifacts[] entry"
        lib_path, shas = e.get("lib_path"), e.get("content_shas")
        if not lib_path or not isinstance(shas, list) or not shas:
            return None, (f"ledger {path} entry {lib_path!r} has no recorded "
                          f"content_shas — cannot prove provenance, refusing to run")
        if len(lib_path.split("/")) < 4:
            return None, (f"ledger {path} entry {lib_path!r} is too shallow to be a "
                          f"safe match anchor — refusing to run")
        out[lib_path] = {
            "content_shas": list(shas),
            "retired_in": e.get("retired_in"),
            "retired_at": e.get("retired_at"),
            "kind": e.get("kind"),
            "dept": e.get("dept"),
        }
    return out, None


# ─── SCAN ─────────────────────────────────────────────────────────────────────

def scan_root(root, ledger, by_basename, hasher, rows, problems):
    """Walk one root looking ONLY for known-retired canonical paths. Read-only."""
    root = Path(root)
    if not root.is_dir():
        return False
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune denied directories (cold backups, VCS, caches) before descending.
        dirnames[:] = [d for d in dirnames if not denied(d)]
        for fname in filenames:
            if fname not in by_basename:
                continue                              # cheap prefilter
            full = Path(dirpath) / fname
            posix = full.as_posix()
            if any(denied(c) for c in full.parts):
                continue
            match = None
            for lib_path in by_basename[fname]:
                if posix.endswith("/" + lib_path):
                    match = lib_path
                    break
            if match is None:
                continue
            if full.is_symlink():
                problems.append({"kind": "UNREADABLE", "path": posix,
                                 "detail": "is a symlink — never followed, never removed"})
                continue
            try:
                real = full.resolve()
                real.relative_to(root.resolve())
            except (OSError, ValueError):
                problems.append({"kind": "UNREADABLE", "path": posix,
                                 "detail": "resolves outside its scan root"})
                continue
            try:
                text = full.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                problems.append({"kind": "UNREADABLE", "path": posix,
                                 "detail": f"cannot read: {e}"})
                continue
            entry = ledger[match]
            sha = hasher.content_sha_of_text(text)
            rows.append({
                "status": "ORPHAN" if sha in entry["content_shas"] else "CONFLICT",
                "path": posix, "root": str(root), "lib_path": match,
                "dept": entry.get("dept"), "kind": entry.get("kind"),
                "content_sha": sha,
                "retired_in": entry.get("retired_in"),
                "retired_at": entry.get("retired_at"),
            })
    return True


# ─── QUARANTINE / RESTORE ─────────────────────────────────────────────────────

def quarantine(qroot, orphans, roots, ledger_path, manifest_path):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch = Path(qroot) / ".orphan-quarantine" / ts
    labels = {str(r): f"{i:02d}-{Path(r).name}" for i, r in enumerate(roots)}
    moved, failures = [], []
    for o in orphans:
        src = Path(o["path"])
        try:
            rel = src.relative_to(Path(o["root"]))
        except ValueError:
            failures.append({"path": str(src), "error": "not under its scan root"})
            continue
        dest = batch / labels.get(o["root"], "root") / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        except (OSError, shutil.Error) as e:
            failures.append({"path": str(src), "error": str(e)})
            continue
        moved.append({
            "original": str(src), "quarantined_to": str(dest),
            "lib_path": o["lib_path"], "dept": o.get("dept"), "kind": o.get("kind"),
            "content_sha": o.get("content_sha"),
            "retired_in": o.get("retired_in"), "retired_at": o.get("retired_at"),
        })
    if moved or failures:
        try:
            batch.mkdir(parents=True, exist_ok=True)
            (batch / "manifest.json").write_text(json.dumps({
                "schema": QUARANTINE_SCHEMA,
                "tool": TOOL,
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
                "roots": [str(r) for r in roots],
                "library_manifest": str(manifest_path),
                "retired_ledger": str(ledger_path),
                "restore": f"python3 {TOOL} --restore {batch}",
                "items": moved, "failures": failures,
            }, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            failures.append({"path": str(batch / "manifest.json"), "error": str(e)})
    return batch, moved, failures


def restore(batch_dir):
    """Move a quarantine batch back. Never clobbers a file that reappeared."""
    man = Path(batch_dir) / "manifest.json"
    try:
        data = json.loads(man.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot read quarantine manifest {man}: {e}", file=sys.stderr)
        print("RESTORE_STATUS ok=0 restored=0 skipped_present=0 failed=0")
        return 2
    if data.get("schema") != QUARANTINE_SCHEMA:
        print(f"FATAL: {man} is not an orphan-quarantine manifest", file=sys.stderr)
        print("RESTORE_STATUS ok=0 restored=0 skipped_present=0 failed=0")
        return 2
    restored = skipped = failed = 0
    for item in data.get("items", []):
        src, dest = Path(item["quarantined_to"]), Path(item["original"])
        if dest.exists():
            print(f"  SKIP (already present): {dest}")
            skipped += 1
            continue
        if not src.is_file():
            print(f"  FAIL (missing from quarantine): {src}", file=sys.stderr)
            failed += 1
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        except (OSError, shutil.Error) as e:
            print(f"  FAIL {dest}: {e}", file=sys.stderr)
            failed += 1
            continue
        print(f"  RESTORED: {dest}")
        restored += 1
    print(f"RESTORE_STATUS ok={0 if failed else 1} restored={restored} "
          f"skipped_present={skipped} failed={failed}")
    return 5 if failed else 0


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Quarantine canonical library files the repo has RETIRED, in the "
                    "trees the updater's wholesale replace never touches. Dry-run "
                    "unless --apply. Never removes client-authored content.")
    ap.add_argument("--root", action="append", default=None)
    ap.add_argument("--quarantine-root", default=None)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--apply", action="store_true",
                    help="actually quarantine (default is DRY-RUN)")
    ap.add_argument("--restore", default=None, metavar="BATCH_DIR")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.restore:
        return restore(args.restore)

    base = oc_root()
    roots = [Path(r) for r in args.root] if args.root else [base / "skills", base / "onboarding"]
    qroot = Path(args.quarantine_root) if args.quarantine_root else base
    manifest_path = Path(args.manifest) if args.manifest else (LIBRARY / "_index.json")
    ledger_path = Path(args.ledger) if args.ledger else (LIBRARY / "_retired.json")

    def fatal(msg):
        print(f"FATAL: {msg}", file=sys.stderr)
        print("RECONCILE_STATUS ok=0 fatal=1 orphans=0 quarantined=0 conflicts=0 problems=0")
        return 2

    hasher = _load_hasher()
    if hasher is None:
        return fatal("hash-content-manifest.py is unavailable — cannot compute content "
                     "provenance, refusing to run")
    live, err = load_live_lib_paths(manifest_path)
    if err:
        return fatal(err)
    ledger, err = load_ledger(ledger_path)
    if err:
        return fatal(err)

    # Contradiction guard: a path may not be BOTH live and retired.
    clash = sorted(set(ledger) & live)
    if clash:
        return fatal("ledger and manifest disagree — listed as BOTH live and retired: "
                     + ", ".join(clash[:5]))

    by_basename = {}
    for lib_path in ledger:
        by_basename.setdefault(lib_path.rsplit("/", 1)[-1], []).append(lib_path)

    rows, problems, scanned = [], [], []
    for r in roots:
        if scan_root(r, ledger, by_basename, hasher, rows, problems):
            scanned.append(str(r))

    orphans = [r for r in rows if r["status"] == "ORPHAN"]
    conflicts = [r for r in rows if r["status"] == "CONFLICT"]

    batch, moved, failures = None, [], []
    if args.apply and orphans:
        batch, moved, failures = quarantine(qroot, orphans, roots, ledger_path, manifest_path)
    moved_paths = {m["original"] for m in moved}

    # ── report ────────────────────────────────────────────────────────────────
    mode = "APPLY" if args.apply else "DRY-RUN (no file moved)"
    print("=" * 78)
    print(f"RETIRED-LIBRARY-FILE RECONCILE — {mode}")
    print(f"roots     : {', '.join(scanned) if scanned else '(none present)'}")
    print(f"manifest  : {manifest_path}")
    print(f"ledger    : {ledger_path}  ({len(ledger)} retired paths)")
    print("=" * 78)
    for r in orphans:
        if not args.apply:
            verb = "WOULD QUARANTINE"
        elif r["path"] in moved_paths:
            verb = "QUARANTINED"
        else:
            verb = "QUARANTINE FAILED"
        print(f"  {verb}: {r['path']}")
        print(f"      retired {(r.get('retired_at') or '?')[:10]} in "
              f"{(r.get('retired_in') or 'a merge commit')[:10]}  ({r.get('kind')})")
    for r in conflicts:
        print(f"  CONFLICT (KEPT): {r['path']} — a RETIRED canonical path whose bytes "
              f"were locally MODIFIED; operator review required", file=sys.stderr)
    for p in problems:
        print(f"  {p['kind']} (KEPT): {p['path']} — {p['detail']}", file=sys.stderr)
    for f in failures:
        print(f"  MOVE FAILED: {f['path']} — {f['error']}", file=sys.stderr)
    if batch and moved:
        print(f"  quarantine batch: {batch}")
        print(f"  restore with    : python3 {TOOL} --restore {batch}")
    print(f"  orphan={len(orphans)} quarantined={len(moved)} "
          f"conflict={len(conflicts)} problems={len(problems)}")

    # ── exit code (2 > 5 > 4 > 10 > 0) ────────────────────────────────────────
    if failures:
        rc = 5
    elif conflicts or problems:
        rc = 4
    elif orphans and not args.apply:
        rc = 10
    else:
        rc = 0
    ok = 1 if rc in (0, 10) else 0
    print(f"RECONCILE_STATUS ok={ok} fatal=0 orphans={len(orphans)} "
          f"quarantined={len(moved)} conflicts={len(conflicts)} problems={len(problems)}")

    receipt = {
        "schema": "openclaw/orphan-reconcile-receipt@1",
        "tool": TOOL,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "apply": args.apply, "rc": rc, "roots": scanned,
        "counts": {"orphan": len(orphans), "quarantined": len(moved),
                   "conflict": len(conflicts), "problems": len(problems)},
        "quarantine_batch": str(batch) if (batch and moved) else None,
        "orphans": [{"path": r["path"], "lib_path": r["lib_path"]} for r in orphans],
        "conflicts": [{"path": r["path"], "lib_path": r["lib_path"]} for r in conflicts],
        "problems": problems,
    }
    try:
        (qroot / ".orphan-reconcile-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    if args.json:
        print(json.dumps(receipt, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
