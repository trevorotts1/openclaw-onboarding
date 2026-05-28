#!/usr/bin/env python3
"""reconcile-legacy-tree.py - v10.15.5 (Mac) / v10.16.5 (VPS)

Closes the Angeleen pattern: a workforce was built (or hand-curated) at a
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

Usage:
  python3 reconcile-legacy-tree.py                      # dry-run
  python3 reconcile-legacy-tree.py --apply              # mutate
  python3 reconcile-legacy-tree.py --legacy <path>      # explicit legacy root
  python3 reconcile-legacy-tree.py --target <path>      # explicit target root
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="mutate files (default: dry-run)")
    ap.add_argument("--legacy", help="explicit legacy root (default: auto-detect)")
    ap.add_argument("--target", help="explicit target departments dir (default: active ZHC)")
    ap.add_argument("--log-dir", default=None)
    args = ap.parse_args()

    target_root = resolve_target_root(args)
    if not target_root or not target_root.is_dir():
        print(f"[reconcile] FATAL: no target departments dir found ({target_root})", file=sys.stderr)
        return 4

    legacy_roots = resolve_legacy_roots(args)
    if not legacy_roots:
        print("[reconcile] No legacy /clawd/departments tree present. Nothing to do.")
        return 0

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
