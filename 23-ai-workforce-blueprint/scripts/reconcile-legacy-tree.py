#!/usr/bin/env python3
"""reconcile-legacy-tree.py - v10.15.5 (Mac) / v10.16.5 (VPS)

Closes the legacy-tree pattern: a workforce was built (or hand-curated) at a
legacy path like /data/clawd/departments/ or ~/clawd/departments/ but the
active workspace lives at $OC_ROOT/workspace/departments/ (or the per-company
ZHC path). Agents read from the active workspace and see stubs or nothing;
the curated content sits at the legacy path, invisible.

This script walks every role folder under the legacy tree and copies content
into the canonical workspace tree, preserving curated live content where it
exists.

Rules:
  - If target doesn't exist  -> COPY legacy file to target.
  - If target exists but IS a stub (heuristic: contains "STUB" or
    "[Step 1 - to be personalized]" or "to be personalized based on
    research") -> OVERWRITE with legacy content (promote legacy -> live).
  - If target exists and is curated -> LEAVE ALONE; log "skipped: live".

Read-only by default. Requires --apply to mutate.

C5 phantom-duplicate mode (--merge-duplicates): reconcile phantom-duplicate
department trees in the ACTIVE workspace — two sibling dirs under departments/
that resolve to the same canonical slug (billing + billing-finance, legal +
legal-compliance). Keeps the canonical winner, layers the loser's unique role
folders into it, and archives the loser (+ any '.bak' dept dirs) OUTSIDE
departments/ under <company>/departments-archive/<ts>/ (never deletes). This mode
does NOT require a legacy /clawd/departments tree.

Usage:
  python3 reconcile-legacy-tree.py                      # dry-run (legacy-path copy)
  python3 reconcile-legacy-tree.py --apply              # mutate (legacy-path copy)
  python3 reconcile-legacy-tree.py --legacy <path>      # explicit legacy root
  python3 reconcile-legacy-tree.py --target <path>      # explicit target root
  python3 reconcile-legacy-tree.py --merge-duplicates            # C5 dry-run
  python3 reconcile-legacy-tree.py --merge-duplicates --apply    # C5 merge+archive
Exit codes: 0 clean/applied · 1 error · 2 dry-run changes pending · 4 no target dir
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Resolve detect_platform via the vendored lib/ (v10.15.4) with fallbacks.
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
for cand in (SKILL_DIR / "lib", SKILL_DIR.parent.parent / "shared-utils", SKILL_DIR / "shared-utils"):
    sys.path.insert(0, str(cand))

try:
    from detect_platform import get_openclaw_paths
except ImportError:
    def get_openclaw_paths():  # type: ignore
        return {}


STUB_PATTERNS = [
    re.compile(r"STUB\s+[-—]", re.IGNORECASE),
    re.compile(r"\[Step\s+1\s*[-—]\s*to be personalized\]", re.IGNORECASE),
    re.compile(r"to be personalized based on research", re.IGNORECASE),
    re.compile(r"<!--\s*placeholder", re.IGNORECASE),
]

LEGACY_CANDIDATES = [
    Path("/data/clawd/departments"),
    Path.home() / "clawd" / "departments",
]


def is_stub(content: str) -> bool:
    head = content[:8192]
    return any(p.search(head) for p in STUB_PATTERNS)


def resolve_target_root(args) -> Path | None:
    if args.target:
        return Path(args.target)
    paths = get_openclaw_paths() or {}
    cand = paths.get("active_zhc_company") or paths.get("zhc_company_root")
    if cand:
        return Path(cand) / "departments"
    # Fallback: most recent company under ZHC root
    workspace = paths.get("workspace_root") or paths.get("clawd_root") or os.path.expanduser("~/clawd")
    zhc = Path(workspace) / "zero-human-company"
    if zhc.is_dir():
        candidates = sorted(
            (d for d in zhc.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0] / "departments"
    return None


def resolve_legacy_roots(args) -> list[Path]:
    if args.legacy:
        return [Path(args.legacy)]
    return [p for p in LEGACY_CANDIDATES if p.is_dir()]


def walk_roles(root: Path):
    """Yield (dept_dir, role_dir) tuples for every role folder under root."""
    for dept in sorted(root.iterdir()):
        if not dept.is_dir() or dept.name.startswith(("_", ".")):
            continue
        for role in sorted(dept.iterdir()):
            if not role.is_dir() or role.name.startswith(("_", ".")):
                continue
            yield dept, role


def file_files(role_dir: Path):
    """List the curated files inside a role folder worth reconciling."""
    out = []
    for name in ("how-to.md", "IDENTITY.md", "SOUL.md", "MEMORY.md", "HEARTBEAT.md"):
        p = role_dir / name
        if p.is_file():
            out.append(p)
    out.extend(sorted(role_dir.glob("0[1-9]-*.md")))
    return out


def _load_department_floor():
    """Import the sibling department-floor.py module for the canonical-slug resolver
    + collision detector (single source of truth — no duplicated slug logic here)."""
    import importlib.util
    fp = SCRIPT_DIR / "department-floor.py"
    spec = importlib.util.spec_from_file_location("department_floor", str(fp))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _role_subdirs(dept_dir: Path):
    """Role folders inside a department dir (non-hidden/underscore subdirs)."""
    if not dept_dir.is_dir():
        return []
    return sorted(
        d.name for d in dept_dir.iterdir()
        if d.is_dir() and not d.name.startswith((".", "_"))
    )


def _pick_winner(cid: str, dirs: list, target_root: Path, df) -> str:
    """
    Choose the canonical WINNER among colliding sibling dirs for canonical id `cid`:
      1. the dir whose name matches the canonical id EXACTLY (normalized) wins
         (e.g. 'billing-finance' beats 'billing', 'legal' beats 'legal-compliance');
      2. else the dir with the MOST role subdirectories wins;
      3. deterministic tie-break: lexicographically-first name.
    """
    exact = [d for d in dirs if df._norm(d) == df._norm(cid)]
    if exact:
        return sorted(exact)[0]
    ranked = sorted(dirs, key=lambda d: (-len(_role_subdirs(target_root / d)), d))
    return ranked[0]


def merge_duplicate_dept_trees(target_root: Path, apply: bool, log, journal) -> dict:
    """
    C5 phantom-duplicate reconcile. When two sibling dirs under departments/
    normalize to the SAME canonical slug (billing + billing-finance, legal +
    legal-compliance, Sales + sales), keep the canonical WINNER, LAYER any role
    folders unique to the loser INTO the winner, then ARCHIVE the loser OUTSIDE
    departments/ (never delete — moved to <company>/departments-archive/<ts>/).
    Phantom '.bak' dept dirs are relocated to the same archive (they poison the
    SOP/substance gate). Read-only unless apply=True.

    Returns a counters dict. Idempotent: a second run finds no collisions.
    """
    df = _load_department_floor()
    nm = df.load_naming_map()
    collisions = df.sibling_slug_collisions(target_root, nm)
    _, backups = df._raw_department_dirs(target_root)

    counters = {"collisions": len(collisions), "merged_losers": 0, "layered_roles": 0,
                "archived_dirs": 0, "backups_archived": 0, "errors": 0,
                "would_merge": 0, "would_archive": 0}

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_root = target_root.parent / "departments-archive" / ts

    def _archive(src: Path, reason: str):
        """Move a dir OUT of departments/ into the archive (apply), or log intent."""
        dest = archive_root / src.name
        journal({"action": "archive", "reason": reason, "src": str(src), "dest": str(dest)})
        if apply:
            try:
                archive_root.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                log(f"[reconcile] ARCHIVE   {src.name} -> {dest} ({reason})")
                return True
            except Exception as e:  # noqa: BLE001 — archive is best-effort, never abort
                log(f"[reconcile] ERROR archive {src}: {e}")
                counters["errors"] += 1
                return False
        else:
            log(f"[reconcile] DRY-RUN ARCHIVE {src.name} -> {dest} ({reason})")
            return False

    for group in collisions:
        cid = group["canonical"]
        dirs = group["dirs"]
        winner = _pick_winner(cid, dirs, target_root, df)
        losers = [d for d in dirs if d != winner]
        log(f"[reconcile] COLLISION canonical '{cid}': keep '{winner}', "
            f"reconcile {len(losers)} loser(s): {', '.join(losers)}")
        win_dir = target_root / winner
        win_roles = set(_role_subdirs(win_dir))
        for loser in losers:
            counters["would_merge" if not apply else "merged_losers"] += 1
            loser_dir = target_root / loser
            # LAYER role folders unique to the loser into the winner.
            for role in _role_subdirs(loser_dir):
                if role in win_roles:
                    continue
                journal({"action": "layer_role", "canonical": cid, "winner": winner,
                         "loser": loser, "role": role})
                if apply:
                    try:
                        shutil.copytree(loser_dir / role, win_dir / role)
                        win_roles.add(role)
                        counters["layered_roles"] += 1
                        log(f"[reconcile] LAYER     {loser}/{role} -> {winner}/{role}")
                    except Exception as e:  # noqa: BLE001
                        log(f"[reconcile] ERROR layer {loser}/{role}: {e}")
                        counters["errors"] += 1
                else:
                    log(f"[reconcile] DRY-RUN LAYER {loser}/{role} -> {winner}/{role}")
            # ARCHIVE the loser tree OUT of departments/ (preserved, never deleted).
            if _archive(loser_dir, f"phantom-duplicate of canonical '{cid}' (kept '{winner}')"):
                counters["archived_dirs"] += 1
            elif not apply:
                counters["would_archive"] += 1

    # Phantom backup dept dirs -> archive (out of the floor/substance scan).
    for b in backups:
        if _archive(target_root / b, "phantom .bak dept dir"):
            counters["backups_archived"] += 1
        elif not apply:
            counters["would_archive"] += 1

    log("")
    log("[reconcile] merge-duplicates summary:")
    for k, v in counters.items():
        log(f"  {k:>20} = {v}")
    if apply and (counters["archived_dirs"] or counters["backups_archived"]):
        log(f"[reconcile] archived trees preserved under: {archive_root}")
    return counters


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="mutate files (default: dry-run)")
    ap.add_argument("--legacy", help="explicit legacy root (default: auto-detect)")
    ap.add_argument("--target", help="explicit target departments dir (default: active ZHC)")
    ap.add_argument("--merge-duplicates", action="store_true",
                    help="C5 mode: merge+archive phantom-duplicate dept trees "
                         "(billing+billing-finance, legal+legal-compliance) instead of "
                         "the legacy-path copy. Read-only unless --apply.")
    ap.add_argument("--log-dir", default=None)
    args = ap.parse_args()

    target_root = resolve_target_root(args)
    if not target_root or not target_root.is_dir():
        print(f"[reconcile] FATAL: no target departments dir found ({target_root})", file=sys.stderr)
        return 4

    log_dir_default = Path.home() / ".openclaw" / "logs"
    if Path("/data/.openclaw").is_dir():
        log_dir_default = Path("/data/.openclaw/logs")
    log_dir = Path(args.log_dir or log_dir_default)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"reconcile-legacy-{ts}.log"
    decision_log = log_dir / f"reconcile-legacy-{ts}.jsonl"

    mode = "APPLY" if args.apply else "DRY-RUN"

    def log(line: str):
        with log_path.open("a") as fh:
            fh.write(line + "\n")
        print(line)

    def journal(decision: dict):
        with decision_log.open("a") as fh:
            fh.write(json.dumps(decision) + "\n")

    # C5 merge-duplicates mode: reconcile phantom-duplicate dept trees in the
    # ACTIVE workspace (does NOT need a legacy /clawd/departments tree). This is
    # the operator-live reconcile RUN that removes existing phantoms.
    if args.merge_duplicates:
        log(f"[reconcile] mode={mode} MERGE-DUPLICATES target_root={target_root}")
        merge_counters = merge_duplicate_dept_trees(target_root, args.apply, log, journal)
        log(f"[reconcile] log:      {log_path}")
        log(f"[reconcile] journal:  {decision_log}")
        if merge_counters["errors"]:
            return 1
        if (not args.apply) and (merge_counters["would_merge"] + merge_counters["would_archive"]) > 0:
            return 2  # informational: phantom-duplicate changes pending
        return 0

    legacy_roots = resolve_legacy_roots(args)
    if not legacy_roots:
        print("[reconcile] No legacy /clawd/departments tree present. Nothing to do.")
        return 0

    log(f"[reconcile] mode={mode} target_root={target_root}")
    log(f"[reconcile] legacy_roots={[str(p) for p in legacy_roots]}")

    counters = {"copied_new": 0, "promoted": 0, "skipped_live": 0,
                "skipped_identical": 0, "would_copy": 0, "would_promote": 0,
                "errors": 0}
    for legacy_root in legacy_roots:
        # Skip if legacy == target (resolve symlinks)
        try:
            if legacy_root.resolve() == target_root.resolve():
                log(f"[reconcile] skip {legacy_root} (same path as target)")
                continue
        except Exception:
            pass

        for dept_dir, role_dir in walk_roles(legacy_root):
            target_dept = target_root / dept_dir.name
            target_role = target_dept / role_dir.name
            for src in file_files(role_dir):
                rel_name = src.name
                target = target_role / rel_name
                decision = {
                    "src": str(src),
                    "target": str(target),
                    "dept": dept_dir.name,
                    "role": role_dir.name,
                    "file": rel_name,
                }
                try:
                    src_content = src.read_text(errors="ignore")
                except Exception as e:
                    log(f"[reconcile] ERROR read {src}: {e}")
                    counters["errors"] += 1
                    continue
                if not target.exists():
                    decision["action"] = "copy_new"
                    counters["would_copy" if not args.apply else "copied_new"] += 1
                    if args.apply:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, target)
                    log(f"[reconcile] {mode} COPY_NEW  {dept_dir.name}/{role_dir.name}/{rel_name}")
                else:
                    try:
                        tgt_content = target.read_text(errors="ignore")
                    except Exception as e:
                        log(f"[reconcile] ERROR read target {target}: {e}")
                        counters["errors"] += 1
                        continue
                    if tgt_content == src_content:
                        decision["action"] = "skip_identical"
                        counters["skipped_identical"] += 1
                        continue
                    if is_stub(tgt_content):
                        decision["action"] = "promote"
                        counters["would_promote" if not args.apply else "promoted"] += 1
                        if args.apply:
                            backup = target.with_suffix(target.suffix + ".pre-reconcile")
                            try:
                                shutil.copy2(target, backup)
                            except Exception:
                                pass
                            target.write_text(src_content)
                        log(f"[reconcile] {mode} PROMOTE   {dept_dir.name}/{role_dir.name}/{rel_name}")
                    else:
                        decision["action"] = "skip_live"
                        counters["skipped_live"] += 1
                        log(f"[reconcile] {mode} SKIP_LIVE {dept_dir.name}/{role_dir.name}/{rel_name}")
                journal(decision)

    log("")
    log("[reconcile] summary:")
    for k, v in counters.items():
        log(f"  {k:>20} = {v}")
    log(f"[reconcile] log:      {log_path}")
    log(f"[reconcile] journal:  {decision_log}")

    if counters["errors"]:
        return 1
    if mode == "DRY-RUN" and (counters["would_copy"] + counters["would_promote"]) > 0:
        return 2  # informational: changes pending
    return 0


if __name__ == "__main__":
    sys.exit(main())
