#!/usr/bin/env python3
"""check-funnel-automation-library-drift.py — drift gate for the funnel + automation libraries.

The 38 funnel templates (06-ghl-install-pages/funnel-templates/) and the 28 automation
templates (44-convert-and-flow-operator/automation-templates/) are now LOAD-BEARING: the
matchers reference them by path/id and the funnel->automation link map pairs them. Nothing
previously protected them from silent rename/delete/desync (library-lockstep.yml only walks
templates/role-library/** and templates/persona-library/**).

This asserts, fail-closed:
  (1) every funnel template on disk is present in the committed funnel catalog-index.json, and
      every indexed funnel id has a real file (no phantom / no orphan);
  (2) every automation template on disk is present in the committed automation catalog-index.json;
  (3) every link-map (funnel-to-automation.json) funnel id resolves to a real funnel template,
      and every referenced automation 'category/id' resolves to a real automation template
      (0 broken refs, 0 phantom funnel ids);
  (4) the committed indexes carry NO operator-local absolute paths (portable);
  (5) the deprecated v1 link map covers the same funnel ids as the canonical v2.

Exit 0 = clean; non-zero = drift (the message names exactly what drifted). stdlib-only.

Usage: python3 scripts/check-funnel-automation-library-drift.py [--repo-root <path>]
"""
from __future__ import annotations

import json
import os
import sys

LEAK_TOKENS = ("/Users/", "/private/tmp", "scratchpad", "blackceomacmini")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _disk_templates(root: str) -> set[str]:
    """Set of 'group/id' for every template .json on disk (skipping _-prefixed)."""
    out = set()
    for group in sorted(os.listdir(root)):
        gdir = os.path.join(root, group)
        if not os.path.isdir(gdir) or group.startswith("_"):
            continue
        for fn in sorted(os.listdir(gdir)):
            if not fn.endswith(".json") or fn.startswith("_"):
                continue
            try:
                doc = _load(os.path.join(gdir, fn))
            except (OSError, json.JSONDecodeError):
                continue
            tid = doc.get("id") or fn[:-5]
            out.add(f"{group}/{tid}")
    return out


def _index_keys(index_path: str) -> set[str]:
    idx = _load(index_path)
    return {f"{t['group']}/{t['id']}" for t in idx.get("templates", [])}


def main(argv: list[str]) -> int:
    repo = os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if "--repo-root" in argv:
        repo = os.path.abspath(argv[argv.index("--repo-root") + 1])

    funnel_root = os.path.join(repo, "06-ghl-install-pages", "funnel-templates")
    funnel_index = os.path.join(repo, "06-ghl-install-pages", "tools", "catalog-index.json")
    auto_root = os.path.join(repo, "44-convert-and-flow-operator", "automation-templates")
    auto_index = os.path.join(auto_root, "_matcher", "catalog-index.json")
    link_v2 = os.path.join(auto_root, "_links", "funnel-to-automation.json")
    link_v1 = os.path.join(auto_root, "_links", "funnel-to-automation-link-map.json")

    errors: list[str] = []

    # (1) funnel disk <-> index parity
    if not os.path.isfile(funnel_index):
        errors.append(f"MISSING committed funnel index: {funnel_index} (run funnel_matcher_cli.py --build-index)")
    else:
        disk = _disk_templates(funnel_root)
        idx = _index_keys(funnel_index)
        if disk - idx:
            errors.append(f"funnel templates on disk but NOT in index (orphans): {sorted(disk - idx)}")
        if idx - disk:
            errors.append(f"funnel ids in index but NO file (phantoms): {sorted(idx - disk)}")
        if len(disk) != 38:
            errors.append(f"expected 38 funnel templates on disk, found {len(disk)}")

    # (2) automation disk <-> index parity
    if not os.path.isfile(auto_index):
        errors.append(f"MISSING committed automation index: {auto_index}")
    else:
        disk = _disk_templates(auto_root)
        idx = _index_keys(auto_index)
        if disk - idx:
            errors.append(f"automation templates on disk but NOT in index (orphans): {sorted(disk - idx)}")
        if idx - disk:
            errors.append(f"automation ids in index but NO file (phantoms): {sorted(idx - disk)}")
        if len(disk) != 28:
            errors.append(f"expected 28 automation templates on disk, found {len(disk)}")

    # (3) link-map integrity (v2 canonical): funnel ids + automation refs resolve
    funnel_ids = {k.split("/", 1)[1] for k in _disk_templates(funnel_root)}
    auto_keys = _disk_templates(auto_root)
    v2 = _load(link_v2)
    lm_funnels = set()
    for link in v2.get("links", []):
        fid = link.get("funnel_template_id")
        lm_funnels.add(fid)
        if fid not in funnel_ids:
            errors.append(f"link map references phantom funnel id: {fid}")
        refs = [link.get("primary_followup")] + list(link.get("secondary_followups", []))
        if "graduation_followup" in link:
            refs.append(link["graduation_followup"])
        for ref in refs:
            if not ref:
                continue
            key = f"{ref.get('category')}/{ref.get('automation_id')}"
            if key not in auto_keys:
                errors.append(f"link map [{fid}] -> BROKEN automation ref: {key}")
    if funnel_ids - lm_funnels:
        errors.append(f"funnel templates NOT covered by the link map: {sorted(funnel_ids - lm_funnels)}")

    # (4) committed indexes carry no operator-local paths
    for label, path in (("funnel index", funnel_index), ("automation index", auto_index)):
        if os.path.isfile(path):
            raw = open(path, encoding="utf-8").read()
            for tok in LEAK_TOKENS:
                if tok in raw:
                    errors.append(f"{label} leaks an operator-local path token '{tok}' (rebuild it portably)")

    # (5b) persona crosswalk: every template persona ref resolves to a REAL canonical persona
    try:
        sys.path.insert(0, os.path.join(repo, "shared-utils"))
        import persona_crosswalk as _pc  # type: ignore[import]
        pres = _pc.scan(funnel_root=funnel_root, auto_root=auto_root)
        if pres["bad_targets"]:
            errors.append(f"persona crosswalk targets not in persona-categories.json: {pres['bad_targets']}")
        unresolved = [f"{r['template']}: {r['ref']!r}" for r in pres["rows"] if not r["ok"]]
        if unresolved:
            errors.append(f"unresolved persona refs ({len(unresolved)}): {unresolved[:5]}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"persona crosswalk validation could not run: {type(exc).__name__}: {exc}")

    # (5) deprecated v1 link map covers the same funnels as v2
    if os.path.isfile(link_v1):
        v1 = _load(link_v1)
        v1_ids = {fid for cat, entries in v1.items() if cat != "_meta"
                  for fid in (entries.keys() if isinstance(entries, dict) else [])}
        if v1_ids != lm_funnels:
            errors.append(f"deprecated v1 link map drifted from v2 coverage: "
                          f"only-v1={sorted(v1_ids - lm_funnels)} only-v2={sorted(lm_funnels - v1_ids)}")

    if errors:
        print("FUNNEL/AUTOMATION LIBRARY DRIFT — FAIL:")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    print(f"OK — funnel(38) + automation(28) libraries, indexes, link map, and persona crosswalk "
          f"are in sync ({len(lm_funnels)} funnels mapped, 0 broken refs, 0 phantoms, "
          f"0 unresolved persona refs, portable indexes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
