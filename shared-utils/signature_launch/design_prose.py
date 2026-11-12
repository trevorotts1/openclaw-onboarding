#!/usr/bin/env python3
"""design-prose.json producer for the Signature Launch pages (fix spec M4 / issue 9, decision D-F).

Until now the one design input Skill 71's request builder takes (``--design-prose``) had no
producer: an operator typed it by hand, so a launch's pages never saw Skill 45. This composes it:

  design direction = Skill 71's page structure for the role(s)
                   + Skill 45's style card LONG tier (when a card is chosen)
                   + Skill 45's page-category rules (_RULES.md)

and records the sha256 of every Skill 45 file it read inside the file
(``design_intelligence.sha256``), so a consumer can tell a composed file from a hand-typed one
and a stale file from a current one. Read-only: nothing in Skill 45 or Skill 71 is written.

The output keys ``notes``, ``traits`` and ``rules_md`` (and ``rules_json``, empty unless a run adds its measured tokens, and covered by the digest) are the ones scripts/build_production_request.py
reads; ``design_intelligence`` is ignored by that builder and read by ``check_design_prose``.

  design_prose.py --launch launch.json --style A|B|C [--card FN-001] [--role thank_you ...] --out design-prose.json

Without ``--role`` the pages are the launch record's route (Skill 49's route law). Exit 0 written,
1 named refusal (AF-DI-ABSENT / AF-DI-PROSE), 2 usage.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "skill45-design-prose/1"
STYLES = ("A", "B", "C")
PROSE_REFUSAL = "AF-DI-PROSE"
_PRIVATE = re.compile(r"Big Bold|framework|\bPain \d|\bSolution \d|\b[2-5][A-C]\b", re.I)  # Skill 71's private labels
_HERE = Path(__file__).resolve().parent
_SKILL_ROOTS = (_HERE.parents[1], Path("~/.openclaw/skills").expanduser(), Path("/data/.openclaw/skills"),
                Path("~/.claude/skills").expanduser())

# role -> (spec file under 71's references/, key path to the sections list)
_ROLE_SPECS = {
    "landing": ("copy-specs/standard-v6.json", ("sections",)),
    "product_selection": ("copy-specs/product-selection-v1.json", ("sections",)),
    "checkout": ("copy-specs/roles/checkout.json", ("sections",)),
    "upsell_1": ("copy-specs/upsell-v6.json", ("sections",)),
    "upsell_2": ("copy-specs/upsell-v6.json", ("sections",)),
    "downsell_1": ("page-structures.json", ("roles", "downsell_1", "sections")),
    "downsell_2": ("page-structures.json", ("roles", "downsell_1", "sections")),
    "thank_you": ("copy-specs/thank-you-v1.json", ("sections",)),
}


@functools.lru_cache(maxsize=None)
def _di():
    """design_intelligence, loaded once so its exception class is one class for every caller."""
    spec = importlib.util.spec_from_file_location("signature_launch_design_intelligence",
                                                  _HERE / "design_intelligence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _refuse(message: str) -> None:
    raise ValueError(f"{PROSE_REFUSAL}: {message}")


def _skill_dir(numbered: str) -> Path:
    bare = numbered.split("-", 1)[1]
    for root in _SKILL_ROOTS:
        for name in (numbered, bare):
            if (root / name).is_dir():
                return root / name
    _refuse(f"skill {numbered} is not installed on this box")
    raise AssertionError  # unreachable


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _refuse(f"{path.name} is missing or unreadable")


def launch_roles(launch: Dict[str, Any]) -> List[str]:
    """The page roles of a launch record, from Skill 49's route law (the one source)."""
    path = _skill_dir("49-signature-funnel") / "scripts" / "compile_launch_route.py"
    spec = importlib.util.spec_from_file_location("design_prose_route_law", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("design_prose_route_law", module)
    scripts = str(path.parent)
    added = scripts not in sys.path
    if added:
        sys.path.insert(0, scripts)
    try:
        spec.loader.exec_module(module)
        return list(module.expected_roles(launch))
    except Exception as exc:  # RouteError and friends: a launch record the route law refuses
        _refuse(f"the launch record has no valid route ({exc})")
    finally:
        if added:
            sys.path.remove(scripts)
    raise AssertionError  # unreachable


def role_structure(role: str, refs: Path) -> str:
    """One line: the role's canonical sections in order, from Skill 71's own spec for that page."""
    if role not in _ROLE_SPECS:
        _refuse(f"{role!r} is not a Skill 71 page role ({', '.join(_ROLE_SPECS)})")
    rel, path = _ROLE_SPECS[role]
    node: Any = _json(refs / rel)
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    if not isinstance(node, list) or not node:
        _refuse(f"Skill 71 has no section list for {role} at {rel}")
    parts, seen = [], {}
    for section in node:
        label = str(section.get("name") or section.get("job") or "").strip().rstrip(".")
        if _PRIVATE.search(label):
            label = ""
        # a clause an earlier section already states is named by reference, never repeated: three pain
        # sections sharing one rule would print an 8-word run three times, which the padding screen refuses
        kept, ref = [], None
        for clause in (c.strip() for c in label.split(";") if c.strip()):
            if clause in seen:
                ref = ref or seen[clause]
            else:
                seen[clause] = section.get("id")
                kept.append(clause)
        label = "; ".join(kept + ([f"same rules as section {ref}"] if ref else []))[:140]
        parts.append(f"{section.get('id')}: {label}" if label else str(section.get("id")))
    return f"{role.replace('_', ' ')} page, {len(node)} sections in this order: " + "; ".join(parts)


def compose(launch: Dict[str, Any], style: str, card_id: Optional[str] = None,
            roles: Optional[List[str]] = None, library: Optional[Path] = None,
            measured: str = "") -> Dict[str, Any]:
    """The design-prose document. ``measured`` is the run's measured design system: appended to ``rules_md``
    here, before the digest is stamped, so the digest always covers it (an edit after this is refused)."""
    di = _di()
    if style not in STYLES:
        _refuse(f"style must be A, B or C, got {style!r}")
    refs = _skill_dir("71-blackceo-signature-page") / "references"
    chosen = list(roles) if roles else launch_roles(launch)
    styles = {s["id"]: s for s in _json(refs / "design-styles.json").get("styles", [])}
    style_rule = ((styles.get(style) or {}).get("prompt_rules") or {}).get("all")
    if not style_rule:
        _refuse(f"Skill 71 design-styles.json has no rule for style {style}")
    base = Path(library) if library is not None else di.library_root()
    card = di.resolve_style_card(card_id, base) if card_id else None
    rules = di.load_page_rules(root=base)
    shas = {"prompt_bands": di.load_prompt_bands(base)["sha256"],
            "negative_prompting": di.load_negative_prompting(base)["sha256"],
            "page_rules": rules["sha256"], "card": card["sha256"] if card else None}
    notes = ("PAGE STRUCTURE (Skill 71 canonical sections, one image slice per section): "
             + " | ".join(role_structure(r, refs) for r in chosen) + ". DESIGN STYLE " + style + ": " + style_rule)
    prose = {"notes": notes,
             "traits": card["long_tier"] if card else "",
             "rules_md": rules["text"].strip() + (("\n" + measured.strip()) if measured.strip() else "")}
    prose["design_intelligence"] = {
        "schema": SCHEMA, "style": style, "roles": chosen, "card_id": card["id"] if card else None,
        "page_rules_category": di.DEFAULT_CATEGORY, "sha256": shas,
        "prose_sha256": _prose_digest(prose)}
    return prose


def _prose_digest(prose: Dict[str, Any]) -> str:
    body = json.dumps({k: prose.get(k, "") for k in ("notes", "traits", "rules_md", "rules_json")}, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def check_design_prose(doc: Any, library: Optional[Path] = None) -> List[str]:
    """Problems with a design-prose document, empty when it was composed here AND is current.

    Refuses a hand-typed file (no ``design_intelligence.sha256``), a file edited after it was composed
    (prose digest), and a file composed against Skill 45 files that have since changed."""
    di = _di()
    meta = doc.get("design_intelligence") if isinstance(doc, dict) else None
    shas = meta.get("sha256") if isinstance(meta, dict) else None
    if meta is None or not isinstance(shas, dict):
        return [f"{PROSE_REFUSAL}: the design prose carries no design_intelligence.sha256, so it was not "
                "composed from Skill 45 (produce it with shared-utils/signature_launch/design_prose.py)"]
    problems: List[str] = []
    if meta.get("prose_sha256") != _prose_digest(doc):
        problems.append(f"{PROSE_REFUSAL}: the design prose was edited after it was composed (prose digest differs)")
    live = {"prompt_bands_sha256": shas.get("prompt_bands"), "negative_prompting_sha256": shas.get("negative_prompting"),
            "page_rules_sha256": shas.get("page_rules"), "card_id": meta.get("card_id"), "card_sha256": shas.get("card"),
            "page_rules_category": meta.get("page_rules_category")}
    problems += di.verify_receipt(live, library)
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Compose design-prose.json from Skill 71 structure + Skill 45 rules.")
    ap.add_argument("--launch", required=True, type=Path, help="the approved launch record (JSON)")
    ap.add_argument("--style", required=True, choices=STYLES)
    ap.add_argument("--card", default=None, help="a registered Skill 45 style card id (optional)")
    ap.add_argument("--role", action="append", default=None, help="a page role; default: the launch route")
    ap.add_argument("--measured", default=None, type=Path, help="the run's measured design system (text file)")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    di = _di()
    try:
        try:
            launch = json.loads(a.launch.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _refuse(f"cannot read the launch record {a.launch.name}")
        if a.measured and not a.measured.is_file():
            _refuse(f"cannot read the measured design system {a.measured.name}")
        measured = a.measured.read_text(encoding="utf-8") if a.measured else ""
        prose = compose(launch, a.style, a.card, a.role, measured=measured)
    except di.DesignIntelligenceError as exc:
        print(exc)
        return 1
    except ValueError as exc:
        print(exc)
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(prose, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"WROTE {a.out.name} style={a.style} card={prose['design_intelligence']['card_id']} "
          f"roles={','.join(prose['design_intelligence']['roles'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
