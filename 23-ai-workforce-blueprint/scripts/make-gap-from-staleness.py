#!/usr/bin/env python3
"""
make-gap-from-staleness.py - build a floor-fill-driver --gap-file from the
detect-stale-artifacts.py verdict (v16.0.2).

This is the BOX-SHIPPABLE source of the floor gap. It reads the per-artifact
staleness verdict that detect-stale-artifacts.py produces (the same JSON the
update path already writes to ~/.openclaw/workspace/.artifact-refresh-queue.json),
and turns every MISSING role / SOP into the gap-map floor-fill-driver.py consumes.

WHY MISSING-ONLY: this closes the "incomplete-floor-after-update" gap - canonical
floor roles/SOPs the new library ships that the box has NO built copy of. STALE
(content drift) and ORPHAN (removed-in-library) are a SEPARATE refresh concern;
floor-fill-driver is skip-existing so it would not touch them anyway. Scoping to
MISSING keeps the materialization precise and additive.

It derives the gap from the role-library's OWN content manifest (via detect-stale,
which compares against templates/role-library/_index.json) - NOT from the
operator-only floor-manifest.json - so every box can run it self-contained.

INPUT (one of):
  positional <detect-json>   a file containing detect-stale-artifacts.py --json output
  --queue <path>             same, but named (defaults to the box refresh queue)
  -                          read the detect-stale JSON from stdin

OUTPUT: the gap JSON written to stdout (or --out <path>):
  { "<dept>": { "kind": "roster"|"named-set",
                "missing_roles": [...],
                "missing_sops":  [...] } }

EXIT CODES
  0  gap written (may be empty {} if nothing is MISSING - floor already complete)
  2  could not read/parse the detect-stale verdict
"""
import argparse
import json
import sys


def build_gap(verdict: dict) -> dict:
    """Turn a detect-stale verdict dict into the floor-fill gap-map."""
    gap = {}
    for item in verdict.get("items", []):
        if item.get("status") != "MISSING":
            continue
        kind = item.get("kind")
        key = item.get("key", "")
        if kind == "role":
            # key == "<dept>/<slug>"
            if "/" not in key:
                continue
            dept, slug = key.split("/", 1)
            ent = gap.setdefault(dept, {"kind": "roster", "missing_roles": [], "missing_sops": []})
            if slug not in ent["missing_roles"]:
                ent["missing_roles"].append(slug)
        elif kind == "sop":
            # key == "<dept>/<sop-slug>"; library file == "<sop-slug>.md"
            if "/" not in key:
                continue
            dept, slug = key.split("/", 1)
            fname = slug if slug.endswith(".md") else f"{slug}.md"
            ent = gap.setdefault(dept, {"kind": "roster", "missing_roles": [], "missing_sops": []})
            ent["kind"] = "named-set"  # presence of a missing SOP => named-set dept
            if fname not in ent["missing_sops"]:
                ent["missing_sops"].append(fname)
        # kind == "dept": the dept-level scaffold is handled by floor-fill-driver
        #   for any dept that appears in the gap; its roles arrive as their own
        #   MISSING role items. A dept with ONLY a missing dept-scaffold and no
        #   missing roles/sops needs no role materialization, so we don't force an
        #   empty entry. kind == "persona": shared pool, not floor-fill's concern.

    # Drop entries that ended up with nothing actionable.
    out = {}
    for dept, ent in gap.items():
        if ent["missing_roles"] or ent["missing_sops"]:
            # only emit missing_sops for named-set depts (floor-fill ignores it otherwise)
            if ent["kind"] != "named-set":
                ent.pop("missing_sops", None)
            out[dept] = ent
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("detect_json", nargs="?", default=None,
                    help="file with detect-stale-artifacts.py --json output, or '-' for stdin")
    ap.add_argument("--queue", default=None,
                    help="path to a detect-stale verdict (e.g. the .artifact-refresh-queue.json)")
    ap.add_argument("--out", default=None, help="write gap JSON here (default: stdout)")
    args = ap.parse_args(argv)

    src = args.detect_json or args.queue
    try:
        if src in (None, "-"):
            verdict = json.load(sys.stdin)
        else:
            with open(src, encoding="utf-8") as f:
                verdict = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: could not read detect-stale verdict ({src or 'stdin'}): {e}", file=sys.stderr)
        return 2

    gap = build_gap(verdict)
    text = json.dumps(gap, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
