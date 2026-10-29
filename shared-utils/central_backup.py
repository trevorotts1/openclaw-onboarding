#!/usr/bin/env python3
"""central_backup.py - ONE central backup folder per box, outside every workspace.

WHY THIS EXISTS. Repair tools used to leave their backup FOLDERS inside the live
department tree: <dept>.bak-<tool>-<stamp>/ next to the real departments,
<workspace>/.floor-backups/<stamp>/, <workspace>/departments-archive/<stamp>/,
<dept>/working/bak-archive-<stamp>/. Measured on one client box: months old, hundreds of
duplicate AGENTS.md / TOOLS.md copies that every scanner and refresher then walked.

LAYOUT.   <backup root>/<tool>/<UTC stamp YYYYmmddTHHMMSSZ>/...
BACKUP ROOT (the rule platform/common.sh OC_BACKUPS and Skill 70 pr_backup_root already use):
    $OPENCLAW_BACKUP_DIR when set, else ~/Downloads/openclaw-backups on macOS,
    else <OpenClaw root>/backups (Hostinger /data/.openclaw, Contabo and bare Linux).
RETENTION. Per tool, the newest $OPENCLAW_BACKUP_KEEP runs are kept (default 3, the same knob
    oc_backup_keep() in update-skills.sh reads). Stamps closer than RUN_GAP seconds are ONE
    run, so a repair that backed up 38 departments seconds apart is kept or pruned as one set,
    never cut in the middle.

CLI (exit 0 ok, 1 a move or prune failed, 2 usage, 4 refused because the user is root):
    central_backup.py migrate [--dry-run] [--root DIR] [--workspace DIR ...]
        MOVE (never delete) backup folders out of the live department trees into the backup
        root, then prune the tools it touched. Idempotent: a second run finds nothing to move.
    central_backup.py run-dir --tool NAME [--dry-run]   print (and create) <root>/<tool>/<stamp>
    central_backup.py prune   --tool NAME [--dry-run]   keep the newest N runs of one tool
    central_backup.py where                             print the backup root

Never prints file contents. Refuses to run as root: a root-owned folder created under a
node-owned volume is exactly what freezes the next prune (see add-department.sh root guard).
Python 3.6+ stdlib only.
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

FMT = "%Y%m%dT%H%M%SZ"
TOOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
RUN_RE = re.compile(r"^(\d{8}T\d{6})Z(?:-\d+)?$")            # a run folder inside <root>/<tool>/
# The SAME definition of "this is a backup, not a department" department-floor.py uses.
BAK_DIR_RE = re.compile(r"\.bak(\b|[-_.]|$)", re.IGNORECASE)
STAMP_RE = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})(?:[T_-]?(\d{2})(\d{2})(\d{2})Z?)?$")
# Backup folders that live INSIDE a real department (the department itself is never moved).
INNER = (
    ("", re.compile(r"^\.(backfill-backup)-(\d{8}T\d{6}Z)$"), "backfill-dept-personalization"),
    ("working", re.compile(r"^(misfiled-scaffold|bak-archive)-(\d{8}T\d{6}Z)$"), None),
)
RESERVED = {"full-backup", "toolsearch-guard", "lean-core-file-system", "install-logs",
            "persist-home", "logs", "skills-rollback", "skills-backup"}
RUN_GAP = 120  # seconds; stamps this close together are one run


def log(msg):
    print("[backups-out] " + msg, flush=True)


def keep_n():
    try:
        n = int(os.environ.get("OPENCLAW_BACKUP_KEEP", "3"))
    except ValueError:
        n = 3
    return max(n, 1)


def oc_root():
    """Same precedence as shared-utils/resolve-oc-root.sh."""
    for k in ("OPENCLAW_ROOT", "OC_ROOT"):
        v = os.environ.get(k, "")
        if v and os.path.isdir(v):
            return Path(v)
    home = Path.home() / ".openclaw"
    data = Path("/data/.openclaw")
    if data.is_dir():
        if home.is_dir() and os.path.realpath(str(data)) == os.path.realpath(str(home)):
            return home
        return data
    return home


def backup_root(root=None):
    v = os.environ.get("OPENCLAW_BACKUP_DIR", "")
    if v:
        return Path(v)
    if sys.platform == "darwin":
        return Path.home() / "Downloads" / "openclaw-backups"
    return Path(root) / "backups" if root else oc_root() / "backups"


def _check_tool(tool):
    if not TOOL_RE.match(tool or "") or tool in RESERVED:
        raise ValueError("unsafe backup tool name: %r" % (tool,))
    return tool


def run_dir(tool, root=None, create=True):
    """A fresh <backup root>/<tool>/<stamp> (never an existing one). Writers call this."""
    tdir = backup_root(root) / _check_tool(tool)
    base = datetime.now(timezone.utc).strftime(FMT)
    run, n = tdir / base, 2
    while run.exists():
        run = tdir / ("%s-%d" % (base, n))
        n += 1
    if create:
        run.mkdir(parents=True)
    return run


def _epoch(name):
    m = RUN_RE.match(name)
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).timestamp()


def prune(tool, root=None, dry_run=False, planned=()):
    """Keep the newest keep_n() runs of one tool; return the run names removed.
    `planned` = run names a dry run would add (counted, never deleted)."""
    tdir = backup_root(root) / _check_tool(tool)
    have = set()
    if tdir.is_dir():
        have = {n for n in os.listdir(str(tdir))
                if RUN_RE.match(n) and (tdir / n).is_dir() and not (tdir / n).is_symlink()}
    clusters, last = [], None
    for n in sorted(have | set(planned)):
        e = _epoch(n)
        if last is None or e - last > RUN_GAP:
            clusters.append([])
        clusters[-1].append(n)
        last = e
    gone = []
    for n in [n for c in clusters[:-keep_n()] for n in c if n in have]:
        if dry_run:
            log("WOULD PRUNE %s (keep=%d)" % (tdir / n, keep_n()))
        else:
            try:
                shutil.rmtree(str(tdir / n))
                log("PRUNE %s (keep=%d)" % (tdir / n, keep_n()))
            except OSError as exc:
                log("WARN could not prune %s: %s" % (tdir / n, exc))
                continue
        gone.append(n)
    return gone


def _is_dir(p):
    return p.is_dir() and not p.is_symlink()


def _kids(d):
    try:
        return sorted((d / n for n in os.listdir(str(d))), key=lambda p: p.name)
    except OSError:
        return []


def _parse(tail, path):
    """(tool, stamp) from the text after '.bak' (or a bare folder name); mtime if no stamp."""
    ts = None
    m = STAMP_RE.search(tail)
    if m:
        try:
            y, mo, d, h, mi, s = m.groups()
            ts = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0),
                          tzinfo=timezone.utc).strftime(FMT)
            tail = tail[:m.start()]
        except ValueError:
            ts = None
    if ts is None:
        ts = datetime.fromtimestamp(os.lstat(str(path)).st_mtime, timezone.utc).strftime(FMT)
    return re.sub(r"[^A-Za-z0-9._-]+", "-", tail).strip("-_.") or "bak", ts


def _discover(root, extra_workspaces):
    """([(src, tool, stamp, nested_name_or_None)], [run-holder dirs]) for every backup folder
    sitting in a live tree. Real department folders are never in the list."""
    cfg_ws = None
    try:
        cfg_ws = json.loads((root / "openclaw.json").read_text(errors="replace"))["agents"]["defaults"]["workspace"]
    except Exception:  # noqa: BLE001 - no/odd config just means "no extra workspace"
        pass
    wss = [root / "workspace"] + [Path(w) for w in extra_workspaces]
    if isinstance(cfg_ws, str) and cfg_ws.strip():
        wss.append(Path(os.path.expanduser(cfg_ws.strip())))
    cc = [c for c in _kids(root / "workspaces") if _is_dir(c)]   # Command Center workspaces
    bases, seen = [], set()
    for w in wss + cc:
        for b in [w] + [c for c in _kids(w / "zero-human-company") if _is_dir(c)]:
            real = os.path.realpath(str(b))
            if os.path.isdir(real) and real not in seen:
                seen.add(real)
                bases.append(Path(real))
    items, holders = [], []
    for b in bases:
        for name, tool in ((".floor-backups", "floor-backups"), ("departments-archive", "departments-archive")):
            if _is_dir(b / name):
                holders.append(b / name)
                items += [(c, tool, _parse(c.name, c)[1], None) for c in _kids(b / name) if _is_dir(c)]
    # a departments/ folder (workspace, company tree) or a Command Center workspace whose
    # children are the departments
    droots = [b / "departments" for b in bases] + [Path(os.path.realpath(str(c))) for c in cc]
    dseen = set()
    for d in droots:
        real = os.path.realpath(str(d))
        if real in dseen or not os.path.isdir(real):
            continue
        dseen.add(real)
        for c in _kids(Path(real)):
            if not _is_dir(c):
                continue
            m = BAK_DIR_RE.search(c.name)
            if m:
                tool, ts = _parse(c.name[m.end():], c)
                items.append((c, tool, ts, c.name))
                continue
            for sub, rx, tool in INNER:   # a real department: only its own known backup folders
                for k in _kids(c / sub if sub else c):
                    mm = rx.match(k.name)
                    if mm and _is_dir(k):
                        items.append((k, tool or mm.group(1), mm.group(2), "%s.%s" % (c.name, k.name.lstrip("."))))
    return items, holders


def migrate(root, workspaces=(), dry_run=False):
    root = Path(root)
    broot = backup_root(root)
    breal = os.path.realpath(str(broot))
    try:
        cfg = (root / "openclaw.json").read_text(errors="replace")
    except OSError:
        cfg = ""
    moved = failed = 0
    runs, taken, done = {}, set(), set()   # tool -> run names this pass adds; dest paths; real srcs
    log("%sOpenClaw root %s -> backup root %s (keep %d per tool)"
        % ("DRY RUN: " if dry_run else "", root, broot, keep_n()))
    items, holders = _discover(root, workspaces)
    for src, tool, ts, nested in items:
        real = os.path.realpath(str(src))
        if real in done or not os.path.isdir(real):
            continue
        done.add(real)
        if breal == real or breal.startswith(real + os.sep):
            continue  # never move the backup root into itself
        # a bare stamp ("20260101T000000Z") would match inside any config path, so run folders
        # are matched as "<holder>/<stamp>"
        if (src.name if nested is not None else src.parent.name + "/" + src.name) in cfg:
            log("SKIP %s: openclaw.json names it, so something still uses it" % src)
            continue
        tool = "dept-" + tool if tool in RESERVED else tool
        run, n = broot / tool / ts, 2
        if nested is None:   # the folder IS the run
            while run.exists() or str(run) in taken:
                run = broot / tool / ("%s-%d" % (ts, n))
                n += 1
            dest = run
        else:                # many folders can share one run
            dest, k = run / nested, 2
            while dest.exists() or str(dest) in taken:
                dest = run / ("%s.%d" % (nested, k))
                k += 1
        taken.add(str(dest))
        runs.setdefault(tool, set()).add(run.name)
        if dry_run:
            log("WOULD MOVE %s -> %s" % (src, dest))
            moved += 1
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        except Exception as exc:  # noqa: BLE001 - a failed move must leave the source untouched
            if os.path.exists(str(src)) and dest.exists():
                shutil.rmtree(str(dest), ignore_errors=True)
            log("FAILED %s -> %s: %s" % (src, dest, exc))
            failed += 1
            continue
        try:
            with open(str(run / "MOVED-FROM.txt"), "a") as fh:
                fh.write("%s\t%s\n" % (dest.name, src))
        except OSError:
            pass
        log("MOVED %s -> %s" % (src, dest))
        moved += 1
    for h in ([] if dry_run else holders):   # leave no empty husk where a backup folder used to be
        try:
            os.rmdir(str(h))
            log("removed the now-empty %s" % h)
        except OSError:
            pass
    for tool in sorted(runs):
        prune(tool, root, dry_run, runs[tool] if dry_run else ())
    log("%s%d backup folder(s), %d failed" % ("would move " if dry_run else "moved ", moved, failed))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    for name in ("migrate", "run-dir", "prune", "where"):
        p = sub.add_parser(name)
        p.add_argument("--dry-run", action="store_true")
        if name == "migrate":
            p.add_argument("--root")
            p.add_argument("--workspace", action="append", default=[])
        if name in ("run-dir", "prune"):
            p.add_argument("--tool", required=True)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_usage(sys.stderr)
        return 2
    if a.cmd in ("migrate", "prune") and os.geteuid() == 0:
        log("REFUSED: running as root. A root-owned folder under the OpenClaw volume blocks the "
            "box user's next prune. Re-run as the box user (docker exec -u node <container> ... on a Docker box).")
        return 4
    try:
        if a.cmd == "where":
            print(backup_root())
        elif a.cmd == "run-dir":
            print(run_dir(a.tool, create=not a.dry_run))
        elif a.cmd == "prune":
            prune(a.tool, dry_run=a.dry_run)
        else:
            return migrate(Path(a.root) if a.root else oc_root(), a.workspace, a.dry_run)
    except ValueError as exc:
        log(str(exc))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
