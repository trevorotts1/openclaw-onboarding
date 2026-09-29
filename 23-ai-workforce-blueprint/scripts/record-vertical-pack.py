#!/usr/bin/env python3
"""
record-vertical-pack.py — record an OPERATOR-DIRECTED vertical-pack declaration
in .workforce-build-state.json, where vertical-derivation-guard.py (phase 3b)
and floor-fill-driver.py read the declared set: verticalPacks.detectedPacks.

WHY: build-workforce.py writes that record only inside a build
(apply_vertical_packs). A box built before the record existed has none, so the
guard fails closed and blocks every update on departments the owner wants. This
is the one supported way to say "the operator declared this pack", with who,
when and why — never a guard bypass: the entry is merged into the same record
the build writes, carries source "operator-directive", and the guard prints it
on every run.

USAGE
  record-vertical-pack.py --pack <pack-id> --by <who> --reason <text>
                          [--at YYYY-MM-DD] [--state PATH] [--dry-run]

  --pack must be a vertical pack in department-naming-map.json. Every other
  build-state key, and every other verticalPacks key and entry, is kept. The
  state file is backed up beside itself (<state>.bak-record-vertical-pack-<ts>)
  and written atomically. Re-recording a pack already declared is a no-op.

EXIT: 0 recorded / already recorded / dry-run; 1 bad input or write failure.
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _guard():
    spec = importlib.util.spec_from_file_location("vertical_derivation_guard",
                                                  HERE / "vertical-derivation-guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _default_state():
    for p in ("/data/.openclaw/workspace/.workforce-build-state.json",
              str(Path.home() / ".openclaw/workspace/.workforce-build-state.json")):
        if os.path.isfile(p):
            return p
    return None


def record(state_path, pack, by, reason, at, dry_run=False):
    """Returns (changed: bool, entry: dict, backup: str|None)."""
    packs = (_guard().load_naming_map().get("vertical_packs") or {})
    if not isinstance(packs.get(pack), dict):
        raise ValueError(f"unknown vertical pack {pack!r}; known: {', '.join(sorted(packs))}")
    if not by.strip() or not reason.strip():
        raise ValueError("--by and --reason are required and may not be empty")
    state = json.loads(Path(state_path).read_text())
    vp = state.get("verticalPacks")
    if vp is not None and not isinstance(vp, dict):
        raise ValueError("build-state verticalPacks is not an object; refusing to overwrite it")
    vp = dict(vp or {})
    detected = list(vp.get("detectedPacks") or [])
    entry = {"pack": pack, "matchedKeywords": [], "source": "operator-directive",
             "by": by.strip(), "at": at, "reason": reason.strip(),
             "recordedAt": datetime.now(timezone.utc).isoformat()}
    if any(isinstance(e, dict) and e.get("pack") == pack for e in detected):
        return False, entry, None
    if dry_run:
        return True, entry, None
    detected.append(entry)
    vp["detectedPacks"] = detected
    vp.setdefault("source", "record-vertical-pack.py (operator directive)")
    state["verticalPacks"] = vp
    backup = f"{state_path}.bak-record-vertical-pack-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    shutil.copy2(state_path, backup)
    tmp = f"{state_path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    shutil.copymode(state_path, tmp)
    os.replace(tmp, state_path)
    return True, entry, backup


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pack", required=True)
    ap.add_argument("--by", required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--at", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--state")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    state = a.state or _default_state()
    if not state or not os.path.isfile(state):
        print("record-vertical-pack: build-state not found (pass --state)", file=sys.stderr)
        return 1
    try:
        changed, entry, backup = record(state, a.pack, a.by, a.reason, a.at, a.dry_run)
    except (ValueError, OSError) as e:
        print(f"record-vertical-pack: {e}", file=sys.stderr)
        return 1
    if not changed:
        print(f"record-vertical-pack: '{a.pack}' is already declared in {state} -- nothing changed")
    elif a.dry_run:
        print(f"[DRY-RUN] would add to {state} verticalPacks.detectedPacks:\n{json.dumps(entry, indent=2)}")
    else:
        print(f"record-vertical-pack: declared '{a.pack}' ({entry['source']}, by {entry['by']}, {entry['at']}) "
              f"in {state}; backup {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
