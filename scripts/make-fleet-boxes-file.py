#!/usr/bin/env python3
"""
make-fleet-boxes-file.py — build the --boxes-file that scripts/fleet-refresh.sh reads.

The fleet's box list lives OUTSIDE this (public) repo, on the operator's machine:

    --roster    canonical membership + platform     (default ~/clawd/accounts/fleet-roster.json)
                boxes.<name>.{provider, kind, registry_id}
    --registry  how to reach each box               (default ~/clawd/fleet-prover/box-registry.json)
                boxes.<id>.{ssh_target | ssh_alias, container, tunnel_id, svc_env_prefix}
    --pins      optional per-box OpenClaw root pins (default ~/clawd/fleet-prover/fleet-roster.json)
                boxes.<id>.openclaw_root

It writes a JSON array (see scripts/fleet-boxes.example.json for the shape) to
--out (default ~/.openclaw/fleet/boxes.json), mode 600. The output holds client
names and hostnames, so it is refused anywhere inside a git work tree.

The operator box (provider "operator" / kind "local") is left out: it is rolled
with `fleet-refresh.sh --local --apply` from its own clone.

Waves: one client box per platform (one Mac, one Hostinger, one Contabo) is
put in wave "first" -- the first by name unless --first names them -- and every
other client box in wave "rest". Roll the first three, check them, then the rest:

    bash scripts/fleet-refresh.sh --wave first --apply
    bash scripts/fleet-refresh.sh --wave rest --apply

Drive backup (if this Mac dies): every run also refreshes a PRIVATE Google Sheet
in the operator's Drive ("OpenClaw fleet box list (private backup)"), one row per
box: name, platform, wave, ssh target, container, exec user, OpenClaw root, tunnel
host, the NAMES of the Cloudflare token env vars, 999 present, last roll result
and date. Env-var NAMES only -- never a secret value. Written through the
operator's Google service account (operator_google.py), never the gws CLI.

    --from-sheet        rebuild boxes.json from that sheet (automatic when the
                        local roster file is missing)
    --record-roll FILE  record a fleet-refresh summary's per-box results
                        (last roll result/date, 999 present) and refresh the sheet;
                        fleet-refresh.sh calls this after every --apply run
    --no-sheet          skip the Drive refresh

Exit: 0 written; 1 bad input / refused output path; 2 written, but some boxes
have no SSH route (listed) and will not be reachable by the roll.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
import operator_google  # noqa: E402

HOME = Path.home()
PLATFORMS = ("mac", "hostinger", "contabo")
SHEET_NAME = "OpenClaw fleet box list (private backup)"
SHEET_COLUMNS = ("name", "platform", "wave", "ssh_target", "container", "docker_exec_user",
                 "openclaw_root", "tunnel_host", "cf_tunnel_id", "cf_access_env_prefix",
                 "cf_token_env_vars", "999_present", "last_roll_result", "last_roll_date")
FLEET_DIR = HOME / ".openclaw/fleet"


def _load_boxes(path: Path, required: bool = True) -> dict:
    if not path.is_file():
        if required:
            raise SystemExit(f"FATAL: not found: {path}")
        return {}
    data = json.loads(path.read_text())
    boxes = data.get("boxes") if isinstance(data, dict) else None
    if not isinstance(boxes, dict):
        raise SystemExit(f"FATAL: {path} has no 'boxes' object")
    return boxes


def build(roster: dict, registry: dict, pins: dict, first: list[str]) -> tuple[list[dict], list[str], list[str]]:
    entries, skipped, unroutable = [], [], []
    for name in sorted(roster):
        box = roster[name]
        provider = str(box.get("provider") or "").lower()
        if provider == "operator" or box.get("kind") == "local":
            skipped.append(f"{name} (operator box: run fleet-refresh.sh --local)")
            continue
        if provider not in PLATFORMS:
            skipped.append(f"{name} (unknown provider {provider!r})")
            continue
        rid = box.get("registry_id") or name
        reg = registry.get(rid) or {}
        target = reg.get("ssh_target") or reg.get("ssh_alias")
        if not target:
            unroutable.append(f"{name} (registry id {rid!r} has no ssh_target/ssh_alias)")
            continue
        entry = {"name": name, "ssh_target": target, "platform": provider}
        if reg.get("container"):
            entry["container"] = reg["container"]
            entry["docker_exec_user"] = reg.get("docker_exec_user") or "node"
        root = (pins.get(rid) or pins.get(name) or {}).get("openclaw_root")
        if root:
            entry["openclaw_root"] = root
        if reg.get("tunnel_id"):
            entry["cf_tunnel_id"] = reg["tunnel_id"]
        if reg.get("svc_env_prefix"):
            entry["cf_access_env_prefix"] = reg["svc_env_prefix"]
        entries.append(entry)

    names = {e["name"] for e in entries}
    unknown = [c for c in first if c not in names]
    if unknown:
        raise SystemExit(f"FATAL: --first names not in the boxes file: {', '.join(unknown)}")
    picks = set(first)
    if not picks:
        for plat in PLATFORMS:
            pick = next((e["name"] for e in entries if e["platform"] == plat), None)
            if pick:
                picks.add(pick)
    for e in entries:
        e["wave"] = "first" if e["name"] in picks else "rest"
    return entries, skipped, unroutable


def _ssh_route(alias: str) -> tuple[str, str]:
    """(tunnel host, Cloudflare token env-var NAMES) from `ssh -G` -- the
    ProxyCommand names its service-token vars; their values are never read."""
    try:
        out = subprocess.run(["ssh", "-G", alias], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return "", ""
    host = next((l.split(None, 1)[1] for l in out.splitlines() if l.startswith("hostname ")), "")
    proxy = next((l for l in out.splitlines() if l.startswith("proxycommand ")), "")
    names = re.findall(r"--service-token-(?:id|secret)\s+\"?\$\{?([A-Z][A-Z0-9_]*)", proxy)
    return (host if "cloudflared" in proxy or "access ssh" in proxy else ""), " ".join(dict.fromkeys(names))


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(path, 0o600)


def sheet_rows(entries: list[dict], last: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(SHEET_COLUMNS)
    for e in entries:
        tunnel, cf = (e.get("tunnel_host", ""), e.get("cf_token_env_vars", ""))
        if e.get("platform") == "mac" and not (tunnel or cf):
            tunnel, cf = _ssh_route(e["ssh_target"])
        run = last.get(e["name"]) or {}
        w.writerow([e.get("name", ""), e.get("platform", ""), e.get("wave", ""), e.get("ssh_target", ""),
                    e.get("container", ""), e.get("docker_exec_user", ""), e.get("openclaw_root", ""),
                    tunnel, e.get("cf_tunnel_id", ""), e.get("cf_access_env_prefix", ""), cf,
                    run.get("nine99", "?"), run.get("result", ""), run.get("date", "")])
    return buf.getvalue()


def entries_from_sheet_csv(text: str) -> list[dict]:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("name") or not row.get("ssh_target"):
            continue
        e = {k: row[k] for k in ("name", "ssh_target", "platform") if row.get(k)}
        for k in ("container", "docker_exec_user", "openclaw_root", "cf_tunnel_id", "cf_access_env_prefix"):
            if row.get(k):
                e[k] = row[k]
        e["wave"] = row.get("wave") or "rest"
        out.append(e)
    return out


def sync_sheet(entries: list[dict]) -> str:
    """Refresh the private Drive copy. Returns a one-line status."""
    if not operator_google.available():
        return "Drive backup skipped: no operator Google account on this machine"
    meta_path = FLEET_DIR / "boxes-sheet.json"
    meta = _read_json(meta_path, {})
    last = _read_json(FLEET_DIR / "last-roll.json", {})
    fid, why = operator_google.upsert_sheet(SHEET_NAME, sheet_rows(entries, last), meta.get("id"))
    if not fid:
        return f"Drive backup NOT refreshed: {why}"
    _write_private(meta_path, json.dumps({"id": fid, "name": SHEET_NAME,
                                          "refreshed": time.strftime("%Y-%m-%dT%H:%M:%S%z")}))
    return f"Drive backup refreshed: sheet '{SHEET_NAME}' ({len(entries)} boxes)"


def record_roll(summary: Path) -> dict:
    """Merge a fleet-refresh summary into ~/.openclaw/fleet/last-roll.json."""
    rows = _read_json(summary, [])
    last = _read_json(FLEET_DIR / "last-roll.json", {})
    today = time.strftime("%Y-%m-%d %H:%M")
    for r in rows if isinstance(rows, list) else []:
        box = r.get("box")
        if not box or box == "local":
            continue
        step = str((r.get("steps") or {}).get("update-999", ""))
        nine = "n" if "999 not installed" in step else ("y" if (r.get("update_999") or {}).get("path") else
                                                       (last.get(box) or {}).get("nine99", "?"))
        last[box] = {"result": r.get("outcome") or r.get("result", ""), "date": today, "nine99": nine}
    _write_private(FLEET_DIR / "last-roll.json", json.dumps(last, indent=2))
    return last


def _inside_git_tree(path: Path) -> bool:
    probe = path.parent
    while not probe.exists():
        probe = probe.parent
    r = subprocess.run(["git", "-C", str(probe), "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", default=str(HOME / "clawd/accounts/fleet-roster.json"))
    ap.add_argument("--registry", default=str(HOME / "clawd/fleet-prover/box-registry.json"))
    ap.add_argument("--pins", default=str(HOME / "clawd/fleet-prover/fleet-roster.json"))
    ap.add_argument("--out", default=str(HOME / ".openclaw/fleet/boxes.json"))
    ap.add_argument("--first", action="append", default=[], metavar="NAME",
                    help="client box to roll in the first wave (repeatable); default: one per platform")
    ap.add_argument("--from-sheet", action="store_true", help="rebuild from the Drive backup sheet")
    ap.add_argument("--record-roll", metavar="SUMMARY", help="record a roll's results and refresh the sheet")
    ap.add_argument("--no-sheet", action="store_true", help="do not refresh the Drive backup")
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()
    if _inside_git_tree(out):
        print(f"FATAL: refusing to write {out}: it is inside a git work tree "
              "(the boxes file holds client names and hostnames).", file=sys.stderr)
        return 1

    if args.record_roll:
        record_roll(Path(args.record_roll))
        entries = _read_json(out, [])
        print(sync_sheet(entries) if entries and not args.no_sheet else "roll recorded")
        return 0

    skipped, unroutable = [], []
    roster = Path(args.roster).expanduser()
    if args.from_sheet or not roster.is_file():
        if not args.from_sheet:
            print(f"roster {roster} not found -- rebuilding from the Drive backup sheet")
        fid = (_read_json(FLEET_DIR / "boxes-sheet.json", {}) or {}).get("id") \
            or operator_google.find_sheet(SHEET_NAME)[0]
        text, why = operator_google.export_sheet_csv(fid) if fid else (None, "sheet not found in Drive")
        if not text:
            print(f"FATAL: cannot rebuild from the Drive sheet: {why}", file=sys.stderr)
            return 1
        entries = entries_from_sheet_csv(text)
        args.no_sheet = True   # never overwrite the backup with what was just read from it
    else:
        entries, skipped, unroutable = build(
            _load_boxes(roster),
            _load_boxes(Path(args.registry).expanduser()),
            _load_boxes(Path(args.pins).expanduser(), required=False),
            args.first,
        )

    _write_private(out, json.dumps(entries, indent=2) + "\n")

    by = {p: sum(1 for e in entries if e["platform"] == p) for p in PLATFORMS}
    print(f"wrote {len(entries)} boxes to {out} (mode 600): "
          + ", ".join(f"{p}={n}" for p, n in by.items()))
    print("first wave (rolled before everyone else): "
          + ", ".join(f"{e['name']} ({e['platform']})" for e in entries if e["wave"] == "first"))
    for s in skipped:
        print(f"  not in file: {s}")
    for u in unroutable:
        print(f"  UNROUTABLE (left out, the roll cannot reach it): {u}", file=sys.stderr)
    if not args.no_sheet:
        print(sync_sheet(entries))
    return 2 if unroutable else 0


if __name__ == "__main__":
    sys.exit(main())
