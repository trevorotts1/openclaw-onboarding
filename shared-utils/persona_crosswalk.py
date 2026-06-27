#!/usr/bin/env python3
"""persona_crosswalk.py — resolve funnel/automation template persona refs to canonical personas.

WHY THIS EXISTS (closes the D5 gap)
-----------------------------------
The 38 funnel templates and 31 automation templates reference their copy persona with a MIX of
short slugs (``funnel-architect``, ``copy-closer``, ``story-brander`` …) and free-text book
descriptions (``"Russell Brunson — Traffic Secrets persona …"``). NONE of those had a crosswalk
to the canonical Skill-22 ``persona-categories.json`` slugs (``russell-brunson-lead-funnels``,
``edwards-copywriting-secrets``, ``miller-building-storybrand`` …). So "copy from the personas"
could not deterministically pull the right persona-blueprint — the vocabulary was unreconciled.

This module is the reconciliation. ``resolve()`` maps any persona ref to a REAL
``persona-categories.json`` id; ``--validate`` proves there are ZERO unresolved refs across every
funnel + automation template (and that every crosswalk target actually exists in the canonical
file). The CI guard + drift checker run ``--validate`` so the vocabulary can't drift again.

Resolution order (most specific first):
  1. the ref already IS a canonical persona id  -> itself
  2. an exact ``slug_map`` hit (the short template slugs)
  3. an ordered ``patterns`` scan over the lowercased ref text (book titles, then framework
     concepts, then author surnames) -> the canonical id of the first pattern that appears

stdlib-only, deterministic, no network.
"""
from __future__ import annotations

import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
DEFAULT_CROSSWALK = os.path.join(_HERE, "persona-crosswalk.json")
DEFAULT_CANONICAL = os.path.join(
    _REPO, "22-book-to-persona-coaching-leadership-system", "persona-categories.json")
DEFAULT_FUNNEL_ROOT = os.path.join(_REPO, "06-ghl-install-pages", "funnel-templates")
DEFAULT_AUTO_ROOT = os.path.join(
    _REPO, "44-convert-and-flow-operator", "automation-templates")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def load_canonical(path: str = DEFAULT_CANONICAL) -> set[str]:
    with open(path, encoding="utf-8") as f:
        return set((json.load(f).get("personas") or {}).keys())


def load_crosswalk(path: str = DEFAULT_CROSSWALK) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _ref_text(ref) -> str:
    """Flatten a persona ref (str | dict) into the text we resolve against."""
    if isinstance(ref, dict):
        for k in ("id", "slug", "label", "name", "persona", "book", "author"):
            v = ref.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return json.dumps(ref, ensure_ascii=False)
    return str(ref or "")


def resolve(ref, canonical: set[str], crosswalk: dict) -> tuple[str | None, str]:
    """Resolve one persona ref to a canonical persona id. Returns (canonical_id|None, how)."""
    text = _ref_text(ref).strip()
    if not text:
        return None, "EMPTY"
    norm = _slug(text)
    if norm in canonical:
        return norm, "canonical-id"
    slug_map = crosswalk.get("slug_map", {})
    if norm in slug_map:
        return slug_map[norm], "slug_map"
    low = text.lower()
    for pat, target in crosswalk.get("patterns", []):
        if pat in low:
            return target, f"pattern:{pat}"
    return None, "UNRESOLVED"


# --------------------------------------------------------------------------- #
# template scanning
# --------------------------------------------------------------------------- #
def _iter_template_files(root: str):
    if not os.path.isdir(root):
        return
    for group in sorted(os.listdir(root)):
        gdir = os.path.join(root, group)
        if not os.path.isdir(gdir) or group.startswith("_"):
            continue
        for fn in sorted(os.listdir(gdir)):
            if fn.endswith(".json") and not fn.startswith("_"):
                yield os.path.join(gdir, fn)


def _persona_refs_funnel(doc: dict) -> list:
    cf = doc.get("copyFramework") or doc.get("copy_framework") or {}
    refs = []
    for k in ("primaryPersona", "primary_persona"):
        if cf.get(k) is not None:
            refs.append(cf[k])
    for k in ("supportingPersonas", "supporting_personas", "secondary_scripts"):
        for v in (cf.get(k) or []):
            refs.append(v)
    return refs


def _persona_refs_auto(doc: dict) -> list:
    refs = []
    cp = doc.get("copy_persona") or doc.get("copyPersona") or {}
    if isinstance(cp, dict):
        for k in ("primary", "secondary"):
            if cp.get(k) is not None:
                refs.append(cp[k])
    elif cp:
        refs.append(cp)
    for k in ("source_books", "sourceBooks", "personas"):
        for v in (doc.get(k) or []):
            refs.append(v)
    return refs


def scan(funnel_root: str = DEFAULT_FUNNEL_ROOT, auto_root: str = DEFAULT_AUTO_ROOT,
         crosswalk_path: str = DEFAULT_CROSSWALK, canonical_path: str = DEFAULT_CANONICAL) -> dict:
    canonical = load_canonical(canonical_path)
    crosswalk = load_crosswalk(crosswalk_path)
    rows = []
    counts = {"funnel_templates": 0, "automation_templates": 0, "refs": 0, "unresolved": 0}

    def _do(path, refs, kind):
        for ref in refs:
            counts["refs"] += 1
            target, how = resolve(ref, canonical, crosswalk)
            ok = target is not None and target in canonical
            if not ok:
                counts["unresolved"] += 1
            rows.append({"kind": kind, "template": os.path.relpath(path, _REPO),
                         "ref": _ref_text(ref)[:70], "target": target, "how": how, "ok": ok})

    for path in _iter_template_files(funnel_root):
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        counts["funnel_templates"] += 1
        _do(path, _persona_refs_funnel(doc), "funnel")
    for path in _iter_template_files(auto_root):
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        counts["automation_templates"] += 1
        _do(path, _persona_refs_auto(doc), "automation")

    # Also validate every crosswalk TARGET resolves to a real canonical persona.
    bad_targets = sorted({t for t in crosswalk.get("slug_map", {}).values() if t not in canonical}
                         | {t for _, t in crosswalk.get("patterns", []) if t not in canonical})
    return {"counts": counts, "rows": rows, "bad_targets": bad_targets, "canonical": sorted(canonical)}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Resolve / validate template persona refs against canonical personas.")
    ap.add_argument("--validate", action="store_true",
                    help="scan all templates; exit non-zero if any ref is unresolved or a target is not canonical")
    ap.add_argument("--list", action="store_true", help="print every ref -> target resolution")
    ap.add_argument("--funnel-root", default=DEFAULT_FUNNEL_ROOT)
    ap.add_argument("--auto-root", default=DEFAULT_AUTO_ROOT)
    ap.add_argument("--crosswalk", default=DEFAULT_CROSSWALK)
    ap.add_argument("--canonical", default=DEFAULT_CANONICAL)
    a = ap.parse_args(argv)

    res = scan(a.funnel_root, a.auto_root, a.crosswalk, a.canonical)
    c = res["counts"]
    unresolved = [r for r in res["rows"] if not r["ok"]]

    if a.list:
        for r in res["rows"]:
            flag = "ok " if r["ok"] else "!! "
            print(f"  {flag}[{r['kind']:<10}] {r['target'] or 'UNRESOLVED':<42} <- {r['ref']!r} ({r['how']})")

    print(f"persona crosswalk: {c['funnel_templates']} funnel + {c['automation_templates']} automation "
          f"templates, {c['refs']} persona refs, {c['unresolved']} unresolved, "
          f"{len(res['bad_targets'])} non-canonical targets")

    if a.validate:
        if res["bad_targets"]:
            print("CROSSWALK TARGET ERROR — these targets are not in persona-categories.json:")
            for t in res["bad_targets"]:
                print(f"  ✗ {t}")
            return 1
        if unresolved:
            print("UNRESOLVED PERSONA REFS — FAIL:")
            for r in unresolved:
                print(f"  ✗ [{r['kind']}] {r['template']}: {r['ref']!r} -> {r['how']}")
            return 1
        print(f"OK — 0 unresolved persona refs; all {c['refs']} resolve to real persona-categories.json entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
