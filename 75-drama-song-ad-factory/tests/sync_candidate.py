#!/usr/bin/env python3
"""U-J01 BUILD tooling: compute the onboarding -> 999 sync candidate, gated.

This tool never writes either tree. It reads both ``scripts/core`` trees,
plans the file actions a final sync would take, and refuses to call the gate
open while any prerequisite fails. The final sync (U-J01 Part B) stays a
separate, explicit act performed only after this gate reports OPEN.

Scope and exclusions match ``twin_sync_prove.tree()`` exactly: every file
under the core root, minus ``__pycache__/`` and ``*.pyc``. Bytes are hashed as
read; nothing is normalised.

Usage:
  python3 -B tests/sync_candidate.py --onb <onb scripts/core> --n99 <n99 scripts/core> [--out FILE]
  python3 -B tests/sync_candidate.py --verify FILE

Exit codes:
  0  gate OPEN (or manifest verified unchanged)
  2  gate BLOCKED (or verified manifest drifted); reasons on stdout and in JSON
  1  tooling error (missing tree, bad manifest)

Gate conditions, all required:
  1. no n99-only path under core - a literal sync would delete it
  2. spend_ledger.py byte-identical on both sides - the money-safety invariant;
     U-B01 must land in onboarding before the 999 copy may be overwritten
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA = "dsaf.sync-candidate/v1"
MONEY_FILE = "spend_ledger.py"


def tree(root):
    """sha256 per file, relative posix path. Caches skipped on both sides."""
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def tree_digest(t):
    return hashlib.sha256("".join(f"{k}  {t[k]}\n" for k in sorted(t)).encode()).hexdigest()


def build_candidate(onb_core, n99_core):
    onb, n99 = tree(onb_core), tree(n99_core)
    files, only_n99 = {}, []
    for rel in sorted(set(onb) | set(n99)):
        ho, hn = onb.get(rel), n99.get(rel)
        if ho and hn:
            action = "same" if ho == hn else "update"
        elif ho:
            action = "add"
        else:
            action = "delete"
            only_n99.append(rel)
        files[rel] = {"action": action, "onb_sha256": ho, "n99_sha256": hn}
    reasons = []
    if only_n99:
        reasons.append(f"n99-only files present in core ({len(only_n99)}): "
                       f"{', '.join(only_n99[:5])} - a literal sync would delete them")
    if MONEY_FILE not in onb or MONEY_FILE not in n99:
        reasons.append(f"money-safety: {MONEY_FILE} missing on one side")
    elif onb[MONEY_FILE] != n99[MONEY_FILE]:
        reasons.append(f"money-safety: {MONEY_FILE} differs "
                       f"(onb={onb[MONEY_FILE]} n99={n99[MONEY_FILE]}) - U-B01 not merged")
    counts = {
        "add": sum(v["action"] == "add" for v in files.values()),
        "delete": len(only_n99),
        "same": sum(v["action"] == "same" for v in files.values()),
        "update": sum(v["action"] == "update" for v in files.values()),
    }
    return {
        "schema": SCHEMA,
        "gate": "BLOCKED" if reasons else "OPEN",
        "reasons": reasons,
        "counts": dict(counts, n99_files=len(n99), onb_files=len(onb)),
        "trees": {"n99_sha256": tree_digest(n99), "onb_sha256": tree_digest(onb)},
        "files": files,
    }


def dump(manifest):
    return json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="U-J01 sync candidate (BUILD tooling).")
    ap.add_argument("--onb", help="onboarding 75-drama-song-ad-factory/scripts/core")
    ap.add_argument("--n99", help="999 .claude/skills/drama-song-ad-factory/scripts/core")
    ap.add_argument("--out", help="write the manifest JSON here")
    ap.add_argument("--verify", help="verify a previously written manifest")
    a = ap.parse_args(argv)

    if not (a.onb and a.n99):
        ap.error("need --onb and --n99 (with or without --verify)")
    onb, n99 = Path(a.onb), Path(a.n99)
    for label, root in (("onb", onb), ("n99", n99)):
        if not root.is_dir():
            print(f"FAIL: {label} core is not a directory: {root}")
            return 1

    m = build_candidate(onb, n99)
    text = dump(m)

    if a.verify:
        try:
            old = Path(a.verify).read_text(encoding="utf-8")
        except OSError as e:
            print(f"FAIL: cannot read manifest {a.verify}: {e}")
            return 1
        if old == text:
            print(f"MANIFEST UNCHANGED {a.verify} gate={m['gate']} counts={m['counts']}")
            return 0
        try:
            prev = json.loads(old)
        except ValueError:
            print("FAIL: manifest is not JSON")
            return 1
        drift = sorted(r for r in set(prev.get("files", {})) | set(m["files"])
                       if prev.get("files", {}).get(r) != m["files"].get(r))
        print(f"MANIFEST DRIFT {a.verify}: {len(drift)} file(s) changed since it was written")
        for r in drift[:10]:
            print(f"  drift: {r}")
        print(f"  trees was={prev.get('trees')} now={m['trees']}")
        return 2
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"WROTE {a.out}")
    print(f"GATE {m['gate']} counts={m['counts']}")
    for r in m["reasons"]:
        print(f"  BLOCKED: {r}")
    print(f"MANIFEST sha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0 if m["gate"] == "OPEN" else 2


if __name__ == "__main__":
    sys.exit(main())
