#!/usr/bin/env python3
"""build-section-map.py — U14 (A-U14, master-spec v2 §A.1.3 / D-A4 Option A).

Regenerates `22-book-to-persona-coaching-leadership-system/personas/
_section-map.json`: a machine-readable crosswalk of every persona blueprint's
section numbering to its TEMPLATE GENERATION and, critically, the ONE section
number that actually carries the "Agent Governance Framework" (the lettered
A/B/C/D subsections: Execution Standard / Quality Control Protocol / Failure
Pattern Recognition / Task Mode Activation Language).

THE HAZARD THIS FIXES (A.1.3): the Command Center dispatch load contract
orders a doer to "Internalize Section 4 (A-D) and Section 7B"
(`persona-dispatch.ts:138-144`). A literal "grab whatever is titled
## Section 4" resolves correctly for Template-B blueprints (Section 4 IS the
Agent Governance Framework there) but WRONGLY for Template-A blueprints
(Section 4 there is "Key Principles" — plain numbered prose with NO A-D
subsections; the real Agent Governance Framework lives at Section 8). The
same load instruction silently loads semantically different, and for
Template A, WRONG material depending on which generation the persona was
synthesized under.

FIX (D-A4 Option A, additive section-map crosswalk — recommended, ratified):
ship this map; `shared-utils/persona_for_job.py`'s `section4_excerpt()`
resolves the CORRECT section per persona via the map instead of a hardcoded
"Section 4" grab. Zero content churn on the 99 blueprints; fully revertable
(delete the map file + revert the one persona_for_job.py commit).

DETECTION METHOD (structural, not title-text): the governing signal is the
lettered subsection group (`### <N>A - ...` / `### <N>B - ...` / ... through
D) under a numbered section — this structure is what "Section 4 (A-D)" in
the dispatch contract actually names. Section TITLE text ("Agent Governance
Framework") is a secondary confirmation only; several Template-A blueprints
carry the identical A-D structure under a slightly different section title
("Task Mode: How to Execute") and are still correctly resolved by the
structural signal.

Usage:
    python3 22-book-to-persona-coaching-leadership-system/scripts/build-section-map.py [--check]

    --check   exit 1 if the committed _section-map.json is stale (does not
              rewrite it) — the CI-guard mode.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL22 = _HERE.parent
_PERSONA_ROOT = _SKILL22 / "personas"
_MAP_PATH = _PERSONA_ROOT / "_section-map.json"

SECTION_HEAD_RE = re.compile(r"^##\s+Section\s+(\d+)\s*[-–—:]\s*(.+?)\s*$")
SUBSECTION_RE = re.compile(r"^###\s+(\d+)([A-D])\s*[-–—:]\s*(.+?)\s*$")

TEMPLATE_A_S1 = "Identity & Voice"
TEMPLATE_B_S1 = "Author Intelligence"

GOVERNANCE_LETTERS = {"A", "B", "C", "D"}


def _scan_persona(bp_path: Path) -> dict:
    text = bp_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    sections: dict[str, str] = {}
    heading_seps: set[str] = set()
    for ln in lines:
        m = SECTION_HEAD_RE.match(ln.strip())
        if m:
            num, title = m.group(1), m.group(2)
            sections[num] = title
            sep_m = re.search(r"Section\s+\d+\s*([-–—:])", ln.strip())
            if sep_m:
                heading_seps.add(sep_m.group(1))

    subsections: dict[str, set] = {}
    for ln in lines:
        m = SUBSECTION_RE.match(ln.strip())
        if m:
            num, letter, _title = m.group(1), m.group(2), m.group(3)
            subsections.setdefault(num, set()).add(letter)

    sec1 = sections.get("1", "")
    if sec1 == TEMPLATE_A_S1:
        template = "A"
    elif sec1 == TEMPLATE_B_S1:
        template = "B"
    else:
        template = "off-template"

    if heading_seps == {"-"}:
        heading_style = "hyphen"
    elif heading_seps in ({"–"}, {"—"}):
        heading_style = "em-dash"
    elif heading_seps:
        heading_style = "mixed:" + ",".join(sorted(heading_seps))
    else:
        heading_style = "none"

    # PRIMARY signal: structural (A-D lettered subsections under one section).
    governance_section = None
    for num, letters in sorted(subsections.items(), key=lambda kv: int(kv[0])):
        if GOVERNANCE_LETTERS.issubset(letters):
            governance_section = int(num)
            break
    # Secondary net: title-text-only match (should not normally fire; kept so
    # a genuinely title-only case is surfaced, never silently dropped).
    if governance_section is None:
        for num, title in sections.items():
            if "governance framework" in title.lower():
                governance_section = int(num)
                break

    principles_section = None
    for num, title in sections.items():
        if "principles" in title.lower():
            principles_section = int(num)
            break

    modal_total = 14  # both templates' canonical shape carry 14 sections
    structure_variant = None
    if len(sections) != modal_total:
        structure_variant = "section-count-%d" % len(sections)

    return {
        "template": template,
        "heading_style": heading_style,
        "total_sections": len(sections),
        "section_titles": {n: sections[n] for n in sorted(sections, key=int)},
        "governance_section": governance_section,
        "principles_section": principles_section,
        "structure_variant": structure_variant,
    }


def build_map() -> dict:
    persona_dirs = sorted(p for p in _PERSONA_ROOT.iterdir() if p.is_dir())
    personas = {}
    for pdir in persona_dirs:
        bp = pdir / "persona-blueprint.md"
        if not bp.exists():
            personas[pdir.name] = {"error": "persona-blueprint.md not found"}
            continue
        personas[pdir.name] = _scan_persona(bp)

    template_counts: dict[str, int] = {}
    heading_style_counts: dict[str, int] = {}
    governance_resolved = 0
    for v in personas.values():
        if "error" in v:
            continue
        template_counts[v["template"]] = template_counts.get(v["template"], 0) + 1
        heading_style_counts[v["heading_style"]] = heading_style_counts.get(v["heading_style"], 0) + 1
        if v["governance_section"] is not None:
            governance_resolved += 1

    return {
        "_meta": {
            "unit": "U14 / A-U14 — Blueprint-generation reconciliation",
            "decision": "D-A4 Option A (additive section-map crosswalk, ratified)",
            "generator": "22-book-to-persona-coaching-leadership-system/scripts/build-section-map.py",
            "total_personas": len(personas),
            "template_counts": template_counts,
            "heading_style_counts": heading_style_counts,
            "governance_section_resolved_count": governance_resolved,
            "notes": [
                "Template A (28 personas): Section 1 = 'Identity & Voice'. The "
                "Agent Governance Framework (lettered A-D subsections: "
                "Execution Standard / Quality Control Protocol / Failure "
                "Pattern Recognition / Task Mode Activation Language) lives at "
                "SECTION 8, NOT Section 4. Section 4 under Template A is 'Key "
                "Principles' — plain numbered prose, no A-D structure.",

                "Template B (71 personas = 67 hyphen-heading + 4 em-dash-"
                "heading): Section 1 = 'Author Intelligence'. The Agent "
                "Governance Framework lives at SECTION 4 — this generation "
                "matches the dispatch load contract's literal 'Section 4 "
                "(A-D)' reference at face value.",

                "4 of the 71 Template-B personas (brunson-marketing-secrets-"
                "blackbook, opara-color-works, rohde-the-sketchnote-workbook, "
                "russell-brunson-the-funnel-hackers-cookbook) use an em-dash "
                "('—') instead of a hyphen ('-') after the section number in "
                "every heading. Structurally identical to Template B "
                "(Section 4 = Agent Governance Framework, 4A-4D present) — a "
                "cosmetic punctuation variant only, not a fourth structural "
                "generation. This IS the 'third minor variant' / '4 blueprints "
                "match neither Section-1 heading' finding in master-spec v2 "
                "§A.1.3 (the literal-string Section-1-heading match used "
                "there does not tolerate the em-dash).",

                "1 persona (butow-ultimate-guide-social-media-marketing) opens "
                "with the Template-A 'Identity & Voice' heading text but uses "
                "a condensed 7-section structure with NO lettered A-D "
                "governance subsections anywhere (closest analog: Section 5 "
                "'Task Mode', which is plain narrative). governance_section is "
                "null for this ONE persona (98/99 resolve). Consumers MUST "
                "treat null as 'no structured governance excerpt on this "
                "blueprint' and degrade honestly (fall back to whatever "
                "literal Section 4 contains, never fabricate governance "
                "content that is not in the file). This is a NEW finding "
                "beyond the spec's 4-blueprint em-dash inventory, surfaced by "
                "this unit's structural (not title-text) scan.",

                "THE FIX: shared-utils/persona_for_job.py's "
                "section4_excerpt(persona_id) reads THIS map's "
                "governance_section for the persona and extracts THAT section "
                "instead of a hardcoded literal 'Section 4' — so a doer that "
                "loads 'Section 4' via the shared entry point receives the "
                "real Agent Governance Framework content under BOTH "
                "generations. A persona absent from the map, or the map file "
                "itself absent (older/back-compat checkout), degrades to the "
                "pre-U14 literal-Section-4 behavior — byte-identical, additive "
                "only.",
            ],
        },
        "personas": personas,
    }


def main(argv: list) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                     help="exit 1 if the committed map is stale; do not write")
    a = ap.parse_args(argv)

    fresh = build_map()
    fresh_text = json.dumps(fresh, indent=2, ensure_ascii=False, sort_keys=False) + "\n"

    if a.check:
        if not _MAP_PATH.exists():
            print("FAIL: %s does not exist" % _MAP_PATH, file=sys.stderr)
            return 1
        current = _MAP_PATH.read_text(encoding="utf-8")
        if current != fresh_text:
            print("FAIL: %s is stale — re-run without --check to regenerate"
                  % _MAP_PATH, file=sys.stderr)
            return 1
        print("OK: %s is current (%d personas)" % (_MAP_PATH, fresh["_meta"]["total_personas"]))
        return 0

    _MAP_PATH.write_text(fresh_text, encoding="utf-8")
    print("wrote %s (%d personas, template_counts=%s)"
          % (_MAP_PATH, fresh["_meta"]["total_personas"], fresh["_meta"]["template_counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
