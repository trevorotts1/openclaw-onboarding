#!/usr/bin/env python3
"""
migrate_zhc_runner.py — PRD item 1.10 core migration logic.

Called by scripts/migrate-zhc-to-master-files.sh.  This module handles all
platform detection, discovery, classification, and execution so the shell
wrapper stays simple and all JSON quoting is handled in Python.

Do NOT call this directly — use scripts/migrate-zhc-to-master-files.sh.

Exit codes:
    0  success (or dry-run completed with no errors)
    1  fatal (cannot detect platform, etc.)
    2  partial (at least one company could not be migrated)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── ANSI colours ──────────────────────────────────────────────────────────────
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
GREEN  = "\033[0;32m"
CYAN   = "\033[0;36m"
BOLD   = "\033[1m"
NC     = "\033[0m"

def red(s):    print(f"{RED}{s}{NC}")
def yellow(s): print(f"{YELLOW}{s}{NC}")
def green(s):  print(f"{GREEN}{s}{NC}")
def cyan(s):   print(f"{CYAN}{s}{NC}")
def bold(s):   print(f"{BOLD}{s}{NC}")


# ── Platform + path resolution ────────────────────────────────────────────────

def _load_paths(shared_utils: Path) -> dict:
    """
    Load platform paths using the canonical get_openclaw_paths() resolver.

    Testing override: set _TEST_LEGACY_ROOTS (colon-separated paths) to inject
    additional legacy roots in fixture-based tests without needing /data/.openclaw.
    This env var is ONLY for test harnesses — never set it in production.
    """
    sys.path.insert(0, str(shared_utils))
    try:
        from detect_platform import get_openclaw_paths, get_legacy_company_roots  # type: ignore
        p = get_openclaw_paths()
        legacy = list(get_legacy_company_roots())

        # Test-only override: allow injecting extra legacy roots via env var.
        _extra = os.environ.get("_TEST_LEGACY_ROOTS", "").strip()
        if _extra:
            for extra_root in _extra.split(":"):
                extra_path = Path(extra_root.strip())
                if extra_path not in legacy:
                    legacy.append(extra_path)

        return {
            "platform":     p["platform"],
            "master_files": p["master_files"],
            "company_root": p["company_root"],
            "workspace":    p["workspace"],
            "build_state":  p["build_state"],
            "dashboard_db": p.get("dashboard_db"),
            "legacy_roots": legacy,
        }
    except SystemExit:
        print("FATAL: Cannot detect OpenClaw platform.", file=sys.stderr)
        print("None of /data/.openclaw, ~/.openclaw, ~/clawd exist.", file=sys.stderr)
        print("Run the OpenClaw installer first.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)


# ── Discovery ─────────────────────────────────────────────────────────────────

def _dept_count(company_dir: Path) -> int:
    d = company_dir / "departments"
    if not d.is_dir():
        return 0
    return sum(1 for p in d.iterdir() if p.is_dir() and not p.name.startswith("."))


def discover(company_root: Path, legacy_roots: list) -> dict:
    """
    Scan canonical root + all legacy roots.

    Returns: {slug: [{"location", "real_location", "mtime", "mtime_human",
                       "dept_count", "is_canonical", "is_symlink"}, ...]}
    """
    manifest: dict = {}

    def scan(root: Path, is_canonical: bool):
        if not root.exists():
            return
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            slug = entry.name
            real_entry = entry.resolve()
            mtime = real_entry.stat().st_mtime
            info = {
                "location":      str(entry),
                "real_location": str(real_entry),
                "mtime":         mtime,
                "mtime_human":   time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
                "dept_count":    _dept_count(real_entry),
                "is_canonical":  is_canonical,
                "is_symlink":    entry.is_symlink(),
            }
            manifest.setdefault(slug, []).append(info)

    scan(company_root, is_canonical=True)
    for lr in legacy_roots:
        scan(Path(lr), is_canonical=False)

    return manifest


def print_manifest(manifest: dict) -> None:
    cyan("── MANIFEST ──────────────────────────────────────────────────────────────")
    if not manifest:
        yellow("  (no companies found in any root — nothing to migrate)")
        print()
        return
    for slug, entries in sorted(manifest.items()):
        print(f"  {slug}  ({len(entries)} location(s)):")
        for e in entries:
            tag = "[canonical]" if e["is_canonical"] else "[legacy]  "
            sym = " (symlink)" if e["is_symlink"] else ""
            print(f"    {tag}  {e['location']}{sym}")
            print(f"             depts={e['dept_count']}  mtime={e['mtime_human']}")
    print()


# ── Classification ────────────────────────────────────────────────────────────

def classify(manifest: dict, company_root: Path) -> dict:
    """
    Returns {"plan": [...], "conflicts": [...]}

    Each plan entry:
        noop:                slug already canonical-only
        move:                simple move from one legacy root
        move_with_conflicts: multiple legacy roots → most-recent is primary,
                             others go to .conflicts/
        conflict_only:       canonical already exists + legacy copies present
    """
    ts_str = time.strftime("%Y%m%dT%H%M%S")
    plan: list = []
    conflicts: list = []

    for slug, entries in sorted(manifest.items()):
        canonical_entries = [e for e in entries if e["is_canonical"] and not e["is_symlink"]]
        legacy_entries    = [e for e in entries if not e["is_canonical"] and not e["is_symlink"]]
        symlink_entries   = [e for e in entries if e["is_symlink"]]

        if canonical_entries and not legacy_entries:
            plan.append({
                "slug":   slug,
                "action": "noop",
                "reason": "canonical-only",
                "source": canonical_entries[0]["location"],
                "dest":   canonical_entries[0]["location"],
            })

        elif not canonical_entries and len(legacy_entries) == 1:
            e = legacy_entries[0]
            plan.append({
                "slug":   slug,
                "action": "move",
                "source": e["location"],
                "dest":   str(company_root / slug),
            })

        elif not canonical_entries and len(legacy_entries) > 1:
            sorted_legacy = sorted(legacy_entries, key=lambda x: x["mtime"], reverse=True)
            primary = sorted_legacy[0]
            others  = sorted_legacy[1:]
            conflict_infos = []
            for o in others:
                src_label = Path(o["location"]).parent.name
                conflict_dest = str(company_root / ".conflicts" / f"{slug}-{src_label}-{ts_str}")
                conflict_infos.append({"source": o["location"], "dest": conflict_dest})
                conflicts.append({"slug": slug, "source": o["location"], "dest": conflict_dest})
            plan.append({
                "slug":            slug,
                "action":          "move_with_conflicts",
                "source":          primary["location"],
                "dest":            str(company_root / slug),
                "conflicts":       conflict_infos,
                "conflict_reason": f"Most-recently-modified primary: {primary['mtime_human']}",
            })

        elif canonical_entries and legacy_entries:
            conflict_infos = []
            for e in legacy_entries:
                src_label = Path(e["location"]).parent.name
                conflict_dest = str(company_root / ".conflicts" / f"{slug}-{src_label}-{ts_str}")
                conflict_infos.append({"source": e["location"], "dest": conflict_dest})
                conflicts.append({"slug": slug, "source": e["location"], "dest": conflict_dest})
            plan.append({
                "slug":            slug,
                "action":          "conflict_only",
                "source":          canonical_entries[0]["location"],
                "dest":            canonical_entries[0]["location"],
                "conflicts":       conflict_infos,
                "conflict_reason": "Canonical exists; legacy copies moved to .conflicts",
            })

        else:
            # Only symlinks (already migrated + symlink left) — nothing to do.
            plan.append({
                "slug":   slug,
                "action": "noop",
                "reason": "symlinks-only",
                "source": entries[0]["location"] if entries else "?",
                "dest":   str(company_root / slug),
            })

    return {"plan": plan, "conflicts": conflicts}


def print_classification(classification: dict) -> None:
    plan = classification["plan"]
    counts: dict = {}
    for item in plan:
        counts[item["action"]] = counts.get(item["action"], 0) + 1

    print(f"  noop (already canonical):        {counts.get('noop', 0)}")
    print(f"  simple move:                     {counts.get('move', 0)}")
    print(f"  move with conflicts:             {counts.get('move_with_conflicts', 0)}")
    print(f"  conflict-only (canonical+legacy):{counts.get('conflict_only', 0)}")
    print()

    for item in plan:
        if item["action"] == "noop":
            print(f"  [noop]     {item['slug']}  ({item.get('reason','already canonical')})")
        elif item["action"] == "move":
            print(f"  [move]     {item['slug']}")
            print(f"             {item['source']}")
            print(f"          -> {item['dest']}")
        elif item["action"] in ("move_with_conflicts", "conflict_only"):
            print(f"  [conflict] {item['slug']}")
            print(f"             primary: {item['source']}")
            print(f"          -> {item['dest']}")
            for c in item.get("conflicts", []):
                print(f"             conflict copy: {c['source']}")
                print(f"                         -> {c['dest']}")
    print()


# ── Execution ─────────────────────────────────────────────────────────────────

def _do_move(src: Path, dst: Path, leave_symlink: bool, errors: list) -> bool:
    """Move src -> dst.  Optionally leave a symlink at src pointing to dst."""
    if not src.exists():
        errors.append(f"source not found: {src}")
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        if leave_symlink:
            try:
                src.symlink_to(dst)
            except Exception as sym_err:
                print(f"  [warn] could not create symlink at {src}: {sym_err}", file=sys.stderr)
        return True
    except Exception as e:
        errors.append(f"move failed {src} -> {dst}: {e}")
        return False


def execute(classification: dict, company_root: Path, log_path: Path) -> dict:
    """
    Apply the migration plan.

    Returns {"new_entries": [...], "errors": [...], "conflicts_tg": [...]}
    Idempotent: skips anything already in the migration log.
    """
    # Load existing log entries for idempotency check
    already_migrated: set = set()
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text())
            for entry in existing.get("migrations", []):
                already_migrated.add(f"{entry['slug']}:{entry['source']}")
        except Exception:
            pass

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    new_entries: list = []
    errors: list = []
    conflicts_tg: list = []

    plan = classification["plan"]

    for item in plan:
        slug   = item["slug"]
        action = item["action"]
        key    = f"{slug}:{item['source']}"

        if action == "noop":
            continue

        if key in already_migrated:
            print(f"  [skip] {slug} already in migration log — idempotent skip")
            continue

        # Move conflict copies first (they go to .conflicts/ without a symlink)
        for c in item.get("conflicts", []):
            csrc = Path(c["source"])
            cdst = Path(c["dest"])
            ck   = f"{slug}:{c['source']}"
            if ck in already_migrated:
                print(f"  [skip] conflict {csrc.name} already logged")
                continue
            if _do_move(csrc, cdst, leave_symlink=False, errors=errors):
                print(f"  [conflict-moved] {csrc.name}  ->  {cdst}")
                conflicts_tg.append(f"  • {slug}: {csrc} -> {cdst}")
                new_entries.append({
                    "slug":        slug,
                    "source":      str(csrc),
                    "dest":        str(cdst),
                    "type":        "conflict",
                    "migrated_at": ts,
                })
            else:
                print(f"  [error] conflict move failed: {csrc}")

        if action == "conflict_only":
            # Primary is already in canonical; just log conflicts above.
            continue

        # Move the primary (with a symlink left at the old location)
        src = Path(item["source"])
        dst = Path(item["dest"])
        if _do_move(src, dst, leave_symlink=True, errors=errors):
            print(f"  [moved] {slug}  {src}  ->  {dst}")
            new_entries.append({
                "slug":         slug,
                "source":       str(src),
                "dest":         str(dst),
                "type":         "primary",
                "migrated_at":  ts,
                "symlink_left": str(src),
            })
        else:
            print(f"  [error] move failed for {slug}: {src}")

    # Persist the migration log (idempotent append)
    company_root.mkdir(parents=True, exist_ok=True)
    existing_log: dict = {"migrations": []}
    if log_path.exists():
        try:
            existing_log = json.loads(log_path.read_text())
        except Exception:
            pass
    existing_log.setdefault("migrations", [])
    existing_log["migrations"].extend(new_entries)
    log_path.write_text(json.dumps(existing_log, indent=2))
    print(f"  [log] Migration log updated: {log_path}")

    if errors:
        print("\n[WARN] Errors during migration:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)

    return {
        "new_entries":  new_entries,
        "errors":       errors,
        "conflicts_tg": conflicts_tg,
    }


# ── Rewire ────────────────────────────────────────────────────────────────────

def rewire(repo_root: Path) -> None:
    """Re-run seed-workspaces.py and sync-md-content-to-db.py, check Gemini index."""
    seed   = repo_root / "32-command-center-setup" / "scripts" / "seed-workspaces.py"
    sync   = repo_root / "23-ai-workforce-blueprint" / "scripts" / "sync-md-content-to-db.py"
    gemini = repo_root / "23-ai-workforce-blueprint" / "scripts" / "gemini-indexer.py"

    for script, label in [(seed, "seed-workspaces.py"), (sync, "sync-md-content-to-db.py")]:
        if script.exists():
            print(f"  Running {label}…")
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True
            )
            for line in (result.stdout + result.stderr).splitlines():
                print(f"    {line}")
            if result.returncode == 0:
                green(f"  {label} OK")
            else:
                yellow(f"  {label} exited {result.returncode} — check output above")
        else:
            yellow(f"  {label} not found at {script}; skipping")

    if gemini.exists():
        print("  Checking Gemini index status…")
        result = subprocess.run(
            [sys.executable, str(gemini), "--status"],
            capture_output=True, text=True
        )
        for line in (result.stdout + result.stderr).splitlines():
            print(f"    {line}")
    print()


# ── Telegram conflict alert ───────────────────────────────────────────────────

def send_telegram_conflict_alert(conflicts_tg: list) -> None:
    if not conflicts_tg:
        green("  No conflicts — no Telegram alert needed.")
        return

    chat_id = os.environ.get("OPENCLAW_OPERATOR_CHAT_ID", "") or \
              os.environ.get("OPERATOR_CHAT_ID", "")
    msg = (
        "⚠️ *ZHC Migration: Conflicts Detected*\n\n"
        "The following companies had duplicate copies across legacy roots.\n"
        "The most-recently-modified copy was promoted; others were preserved under `.conflicts/`\n"
        "Please review:\n\n"
        + "\n".join(conflicts_tg)
    )

    if not chat_id:
        yellow("  OPENCLAW_OPERATOR_CHAT_ID / OPERATOR_CHAT_ID not set — Telegram alert skipped.")
        yellow("  Conflict list:")
        for line in conflicts_tg:
            print(f"    {line}")
        return

    # Try openclaw CLI first (preferred per PRD / memory notes)
    try:
        result = subprocess.run(
            ["openclaw", "message", "send", "--channel", "telegram",
             "-t", chat_id, "--text", msg],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            green("  Telegram conflict alert sent to operator.")
        else:
            yellow("  Could not send Telegram alert via openclaw — check token.")
            yellow("  Conflict list:")
            for line in conflicts_tg:
                print(f"    {line}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        yellow("  openclaw CLI not available; conflict list written to stdout only.")
        yellow("  Conflicts:")
        for line in conflicts_tg:
            print(f"    {line}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="PRD 1.10 — migrate ZHC companies to the canonical master-files root"
    )
    parser.add_argument("--shared-utils", required=True,
                        help="Path to the shared-utils directory")
    parser.add_argument("--repo-root",    required=True,
                        help="Path to the onboarding repo root")
    parser.add_argument("--apply",        action="store_true",
                        help="Actually move files (default is dry-run)")
    args = parser.parse_args()

    shared_utils = Path(args.shared_utils)
    repo_root    = Path(args.repo_root)
    apply        = args.apply

    if apply:
        bold("=== migrate-zhc-to-master-files.sh  [--apply MODE] ===")
    else:
        bold("=== migrate-zhc-to-master-files.sh  [DRY-RUN MODE — nothing will move] ===")
    print()

    # ── Step 1: Resolve canonical + legacy roots ──────────────────────────────
    paths        = _load_paths(shared_utils)
    company_root = Path(paths["company_root"])
    legacy_roots = paths["legacy_roots"]

    print(f"Platform:      {paths['platform']}")
    print(f"Master files:  {paths['master_files']}")
    print(f"Canonical ZHC: {company_root}")
    print(f"Workspace:     {paths['workspace']}")
    print()

    # ── Step 2: Discover ──────────────────────────────────────────────────────
    bold("[1/5] Discovering companies in all known roots…")
    manifest = discover(company_root, legacy_roots)
    print()
    print_manifest(manifest)

    # ── Step 3: Classify ──────────────────────────────────────────────────────
    bold("[2/5] Classifying companies…")
    classification = classify(manifest, company_root)
    print_classification(classification)

    # ── Step 4: Execute ───────────────────────────────────────────────────────
    bold("[3/5] Applying moves…")

    if not apply:
        yellow("  DRY-RUN: no files were moved.  Pass --apply to execute.")
        print()
        log_path      = None
        exec_result   = None
        conflicts_tg  = []
    else:
        log_path    = company_root / ".migration-log.json"
        exec_result = execute(classification, company_root, log_path)
        conflicts_tg = exec_result["conflicts_tg"]
        print()

    # ── Step 5: Rewire ────────────────────────────────────────────────────────
    bold("[4/5] Rewiring dashboard + persona index…")

    if not apply:
        yellow("  DRY-RUN: rewire skipped.")
        print()
    else:
        rewire(repo_root)

    # ── Step 6: Notifications ─────────────────────────────────────────────────
    bold("[5/5] Notifications…")

    if not apply:
        yellow("  DRY-RUN: no notifications sent.")
        print()
    else:
        send_telegram_conflict_alert(conflicts_tg)
        if exec_result and exec_result["errors"]:
            red("  ERRORS during migration:")
            for e in exec_result["errors"]:
                print(f"    {e}")
        print()

    # ── Final summary ─────────────────────────────────────────────────────────
    print()
    if apply:
        green("=== Migration complete ===")
        print()
        print(f"  Canonical root: {company_root}")
        if log_path and log_path.exists():
            try:
                log_data = json.loads(log_path.read_text())
                primary_count = sum(
                    1 for e in log_data.get("migrations", [])
                    if e.get("type") == "primary"
                )
                print(f"  Companies migrated (primary moves): {primary_count}")
            except Exception:
                pass
        print()
        print("  Next steps:")
        print("    1. Verify all departments are visible in the Command Center dashboard")
        print("    2. Test persona selection: python3 persona-selector-v2.py --department <dept> --task 'test' --format json")
        print("    3. One release from now, run the retire step (remove legacy candidate lists from detect_platform.py)")
        print()
        print(f"  Migration log: {company_root}/.migration-log.json")
        if exec_result and exec_result["errors"]:
            return 2
    else:
        yellow("=== DRY-RUN complete — nothing was moved ===")
        print()
        print("  Review the manifest above, then run with --apply to migrate.")
        print()
        print("  IMPORTANT: The resolver checks canonical FIRST, legacy roots second.")
        print("  When a legacy root is used as fallback, a loud warning is printed.")
        print("  Run --apply to silence those warnings permanently.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
