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

Exit: 0 written; 1 bad input / refused output path; 2 written, but some boxes
have no SSH route (listed) and will not be reachable by the roll.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
PLATFORMS = ("mac", "hostinger", "contabo")


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
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()
    if _inside_git_tree(out):
        print(f"FATAL: refusing to write {out}: it is inside a git work tree "
              "(the boxes file holds client names and hostnames).", file=sys.stderr)
        return 1

    entries, skipped, unroutable = build(
        _load_boxes(Path(args.roster).expanduser()),
        _load_boxes(Path(args.registry).expanduser()),
        _load_boxes(Path(args.pins).expanduser(), required=False),
        args.first,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(out.parent, 0o700)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(entries, fh, indent=2)
        fh.write("\n")
    os.chmod(out, 0o600)

    by = {p: sum(1 for e in entries if e["platform"] == p) for p in PLATFORMS}
    print(f"wrote {len(entries)} boxes to {out} (mode 600): "
          + ", ".join(f"{p}={n}" for p, n in by.items()))
    print("first wave (rolled before everyone else): "
          + ", ".join(f"{e['name']} ({e['platform']})" for e in entries if e["wave"] == "first"))
    for s in skipped:
        print(f"  not in file: {s}")
    for u in unroutable:
        print(f"  UNROUTABLE (left out, the roll cannot reach it): {u}", file=sys.stderr)
    return 2 if unroutable else 0


if __name__ == "__main__":
    sys.exit(main())
