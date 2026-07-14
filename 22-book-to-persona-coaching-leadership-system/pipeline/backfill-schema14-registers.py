#!/usr/bin/env python3
"""
backfill-schema14-registers.py — A-U3 one-time schema-1.3 -> 1.4 backfill.

WHAT THIS DOES
---------------
Stamps three additive scalar fields — `emotional_register`,
`audience_resonance`, `conversion_style` — onto every persona in
persona-categories.json from the hand-reviewed, source-grounded map in
schema14_register_assignments.py (see that module's docstring for HOW each
value was derived — read from each persona's own already-catalogued
voice_style, never invented from the name). Bumps `schemaVersion` 1.3 -> 1.4
and adds the three top-level controlled-vocabulary arrays
(`emotionalRegisterTags`/`audienceResonanceTags`/`conversionStyleTags`) the
new fields are checked against by `persona_blend.validate_catalog_tags`
(23-ai-workforce-blueprint/scripts/persona_blend.py) and, at synthesis time,
by `orchestrator._synthesis_system()`'s live vocab injection.

This mirrors the v6.17.0 one-time schema-1.2 -> 1.3 backfill: a run-once
authoring pass over the EXISTING catalog (not a live pipeline component —
`orchestrator.py`'s D6 duality-tag stamping is what carries these three
fields forward for personas synthesized AFTER this backfill lands).

ADDITIVE / IDEMPOTENT / NEVER-TO-ZERO
--------------------------------------
- Every persona already carries voice_style (verified: 99/99) — this backfill
  adds three MORE fields, touches no existing field, drops no persona.
- Re-running is a no-op on an already-backfilled catalog UNLESS --force is
  given (default: skip a slug that already carries all three fields, so a
  partial hand-edit downstream is never silently clobbered).
- A slug present in the catalog but absent from ASSIGNMENTS is left
  untouched and reported — never a fabricated guess.
- Fails loudly (non-zero exit) and writes NOTHING if the post-write catalog
  does not validate clean under persona_blend.validate_catalog_tags — no
  half-valid catalog is ever committed to disk.

USAGE
-----
    python3 backfill-schema14-registers.py [--categories PATH] [--force] [--dry-run]

Exit codes: 0 ok; 2 usage/IO error; 3 an assignment failed the vocab gate;
4 a persona in the catalog has no assignment (report-only, does not block
unless --strict is also given).
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_DEFAULT_CATEGORIES = _HERE.parent / "persona-categories.json"
_PERSONA_BLEND = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts" / "persona_blend.py"


def _load_by_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--categories", type=Path, default=_DEFAULT_CATEGORIES,
                    help="path to persona-categories.json (default: the canonical "
                         "skill-22 seed)")
    ap.add_argument("--force", action="store_true",
                    help="re-stamp a slug even if it already carries all three "
                         "schema-1.4 fields (default: skip, never clobber)")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any catalog slug has no entry in "
                         "ASSIGNMENTS (default: report and continue — a slug "
                         "added after this backfill was authored is not a "
                         "regression)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change; write nothing")
    args = ap.parse_args(argv)

    assignments_mod = _load_by_path(_HERE / "schema14_register_assignments.py",
                                    "schema14_register_assignments")
    ASSIGNMENTS = assignments_mod.ASSIGNMENTS
    EMOTIONAL_REGISTER_TAGS = assignments_mod.EMOTIONAL_REGISTER_TAGS
    AUDIENCE_RESONANCE_TAGS = assignments_mod.AUDIENCE_RESONANCE_TAGS
    CONVERSION_STYLE_TAGS = assignments_mod.CONVERSION_STYLE_TAGS

    if not args.categories.exists():
        sys.stderr.write(f"FATAL: {args.categories} not found\n")
        return 2
    catalog = json.loads(args.categories.read_text())
    personas = catalog.get("personas") or {}
    if not isinstance(personas, dict):
        sys.stderr.write("FATAL: catalog['personas'] is not an object\n")
        return 2

    unassigned = sorted(set(personas) - set(ASSIGNMENTS))
    stamped, skipped = [], []
    for slug, (register, resonance, closer) in ASSIGNMENTS.items():
        entry = personas.get(slug)
        if entry is None:
            continue  # an assignment for a slug no longer in the catalog — ignore
        already = all(f in entry for f in
                      ("emotional_register", "audience_resonance", "conversion_style"))
        if already and not args.force:
            skipped.append(slug)
            continue
        entry["emotional_register"] = register
        entry["audience_resonance"] = resonance
        entry["conversion_style"] = closer
        stamped.append(slug)

    # Insert the three new top-level vocab arrays alongside their v1.3
    # siblings (audienceTags/topicTags) rather than appending at the very end
    # after 'personas'/'lastUpdated' — cosmetic only (JSON key order is not
    # semantically meaningful here), but keeps the file's existing top-level
    # grouping convention intact for a human reading the diff.
    _personas_val = catalog.pop("personas", personas)
    _last_updated_val = catalog.pop("lastUpdated", None)
    catalog["emotionalRegisterTags"] = EMOTIONAL_REGISTER_TAGS
    catalog["audienceResonanceTags"] = AUDIENCE_RESONANCE_TAGS
    catalog["conversionStyleTags"] = CONVERSION_STYLE_TAGS
    catalog["personas"] = _personas_val
    if _last_updated_val is not None:
        catalog["lastUpdated"] = _last_updated_val
    if str(catalog.get("schemaVersion", "")) in ("1.3", "1.2", "1.1", "1.0", ""):
        catalog["schemaVersion"] = "1.4"

    # Validate through the SAME rulebook the matcher / D6 pipeline enforce
    # at read-time — never write a catalog this backfill itself would reject.
    pb = _load_by_path(_PERSONA_BLEND, "persona_blend_backfill_gate")
    result = pb.validate_catalog_tags(catalog)
    if not result["ok"]:
        sys.stderr.write("FATAL: post-backfill catalog failed validate_catalog_tags:\n")
        for e in result["errors"]:
            sys.stderr.write(f"  ✗ {e}\n")
        return 3

    print(f"stamped: {len(stamped)}  skipped (already stamped): {len(skipped)}  "
          f"unassigned (no map entry): {len(unassigned)}")
    if unassigned:
        for slug in unassigned:
            print(f"  UNASSIGNED: {slug}")
        if args.strict:
            sys.stderr.write("FATAL (--strict): unassigned slugs present\n")
            return 4

    total = len(personas)
    complete = sum(
        1 for p in personas.values()
        if isinstance(p, dict) and all(
            f in p for f in ("emotional_register", "audience_resonance", "conversion_style")
        )
    )
    print(f"coverage: {complete}/{total} personas carry all three schema-1.4 fields")
    print(f"validate_catalog_tags: ok={result['ok']} checked={result['checked']} "
          f"schema={result['schema']}")

    if args.dry_run:
        print("--dry-run: not writing")
        return 0

    if stamped:
        catalog["lastUpdated"] = datetime.date.today().isoformat()
    args.categories.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.categories}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
