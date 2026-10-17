#!/usr/bin/env python3
"""Validate a copy manuscript's structure against a machine-readable copy spec.

Implements FIX-PLAN Item 18 (as amended by Amendment 6 C4/C5 and Part D).
The spec files in references/copy-specs/ are extracted from the v6 guides
(Item 17); this script is deliberately guide-agnostic: every number, unit,
CTA position, and status (hard vs target) comes from the spec, never from
code. A limit is checked in the unit the spec declares (words or chars),
under the spec's counting convention:

  words = whitespace-separated tokens after stripping markers (hyphenated
          terms, contractions, and "Q&A" each count as one word);
  chars = the visible components joined with one space, counting letters,
          punctuation, and spaces.

The convention implementation in this file is verified against the guides'
own measured examples (tests/fixtures/copy_examples/: 81 per-section lesson
examples plus both guides' assembled path B manuscripts reproduce the
published counts exactly).

Usage:
  validate_copy_structure.py <run_dir> --spec references/copy-specs/standard-v6.json
  validate_copy_structure.py path/to/internal-manuscript.md --spec <spec.json>
                             [--manifest path/to/copy-manifest.json] [--json]

Exit codes: 0 = no hard failure (warnings/flags allowed), 1 = hard failure,
2 = usage / IO / spec error.

What this script does NOT do: judge quality. Emotional-quality criteria and
the either/or rules live in the spec as kind "qualitative"/"conditional";
where a mechanical prefilter exists it emits FLAG lines for the reviewer,
never failures. Public-copy leakage stays with validate_public_copy.py.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Counting core (the guides' declared convention; fixture-verified)
# --------------------------------------------------------------------------

CTA_RE = re.compile(r"\[CTA (BUTTON|MICROCOPY):\s*(.*?)\]", re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
SECTION_RE = re.compile(r"^##\s+Section\s+([0-9]+[A-Z]?)\s*[:\-]\s*(.*)$")
PART_RE = re.compile(r"^###\s+Part\s+(\d+)\s*[:\-]\s*(.*)$")
CHILD_RE = re.compile(r"^###\s+([0-9]+[A-Z])\s*[:\-]\s*(.*)$")
LABEL_LINE_RE = re.compile(r"^\*\*.* - internal (part|panel) label\*\*$")
FENCE_RE = re.compile(r"^(`{3,4})\s*[A-Za-z]*$")


def strip_formatting(text):
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", text)
    return text.replace("`", "")


def _clean(text):
    return " ".join(strip_formatting(text).split())


class Unit:
    __slots__ = ("text", "kind", "section", "child", "part", "step_no")

    def __init__(self, text, kind, section, child=None, part=None, step_no=None):
        self.text = text
        self.kind = kind          # para | bullet | step | cta_button | cta_microcopy
        self.section = section
        self.child = child        # e.g. "5A" while inside that child of Section 5
        self.part = part          # founder-letter part number while inside Section 12
        self.step_no = step_no

    def __repr__(self):
        return f"<Unit {self.kind} S{self.section} {self.text[:30]!r}>"


def parse_manuscript(text):
    """Split a private-review manuscript into typed copy units.

    Returns (units, section_order, structure_notes). Framework headings,
    internal labels, HTML comments (the internal notes), and formatting
    markers are excluded per the guides' counting convention; visual-panel
    and export-part identifiers are not sections and never become blocks.
    """
    text = COMMENT_RE.sub("", text)
    units = []
    section_order = []
    structure_notes = []
    section = None
    child = None
    part = None
    para = []

    def flush():
        if para and section is not None:
            t = _clean(" ".join(para))
            if t:
                units.append(Unit(t, "para", section, child, part))
        para.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if FENCE_RE.match(line):
            continue
        m = SECTION_RE.match(line)
        if m:
            flush()
            section = m.group(1)
            child = None
            part = None
            if section not in section_order:
                section_order.append(section)
            else:
                structure_notes.append(f"duplicate section heading: Section {section}")
            continue
        if line.startswith("## "):
            # A non-framework top-level heading ends the current section block.
            flush()
            section = None
            child = None
            part = None
            continue
        mp = PART_RE.match(line)
        if mp and section == "12":
            flush()
            part = int(mp.group(1))
            continue
        mc = CHILD_RE.match(line)
        if mc and section is not None and mc.group(1).startswith(section) and mc.group(1) != section:
            flush()
            child = mc.group(1)
            continue
        if line.startswith("#"):
            continue  # any other heading is a label, not copy
        if LABEL_LINE_RE.match(line):
            continue  # bold internal part/panel label line
        if not line or line == "---":
            flush()
            continue
        if section is None:
            continue  # document title / front matter: excluded by the convention

        # CTA markers become their own units; the surrounding text stays copy.
        pieces = []
        last = 0
        for cm in CTA_RE.finditer(line):
            pieces.append(("text", line[last:cm.start()]))
            pieces.append(("cta_button" if cm.group(1) == "BUTTON" else "cta_microcopy",
                           cm.group(2)))
            last = cm.end()
        pieces.append(("text", line[last:]))

        for kind, chunk in pieces:
            if kind != "text":
                flush()
                t = _clean(chunk)
                if t:
                    units.append(Unit(t, kind, section, child, part))
                continue
            chunk = chunk.strip()
            if not chunk:
                continue
            mb = re.match(r"^[-*]\s+(.*)$", chunk)
            mn = re.match(r"^(\d+)\.\s+(.*)$", chunk)
            if mb:
                flush()
                t = _clean(mb.group(1))
                if t:
                    units.append(Unit(t, "bullet", section, child, part))
            elif mn:
                flush()
                t = _clean(mn.group(2))
                if t:
                    units.append(Unit(t, "step", section, child, part,
                                      step_no=int(mn.group(1))))
            else:
                para.append(chunk)
    flush()
    return units, section_order, structure_notes


def units_from_markdown(md):
    """Count-only view used by the fixture tests: (units, markers) for a
    block of copy markdown with no section structure."""
    units, _order, _notes = parse_manuscript("## Section 1: fixture\n\n" + md)
    markers = [(u.kind, u.text) for u in units if u.kind.startswith("cta_")]
    return units, markers


def count_words(units):
    return sum(len(u.text.split()) for u in units)


def count_chars(units):
    texts = [u.text for u in units]
    return len(" ".join(texts)) if texts else 0


def measure(units, unit):
    return count_words(units) if unit == "words" else count_chars(units)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

class Report:
    def __init__(self):
        self.fails = []
        self.warns = []
        self.flags = []
        self.infos = []
        self.counts = {}   # section id -> {"words": n, "chars": n, ...}


def _band_text(lim):
    lo = lim.get("min")
    hi = lim.get("max")
    if lo is not None and hi is not None:
        return f"{lo}-{hi}"
    if hi is not None:
        return f"at most {hi}"
    return f"at least {lo}"


def check_limit(rep, value, lim, label, failed_keys):
    """Apply one spec limit. kind hard -> FAIL, target -> WARN,
    descriptive -> never reported. Returns True if a FAIL was recorded."""
    kind = lim.get("kind", "hard")
    if kind == "descriptive":
        return False
    lo, hi = lim.get("min"), lim.get("max")
    if (lo is None or value >= lo) and (hi is None or value <= hi):
        return False
    key = (lim.get("unit"), lim.get("scope"))
    if kind == "hard":
        rep.fails.append(
            f"{label}: {value} {lim.get('unit')} is outside the hard band "
            f"{_band_text(lim)} (spec source: {lim.get('source', 'n/a')})")
        failed_keys.add(key)
        return True
    if key in failed_keys:
        return False  # the hard failure on the same measure already says it
    rep.warns.append(
        f"{label}: {value} {lim.get('unit')} is outside the suggested band "
        f"{_band_text(lim)} (guidance in the guide, not a failure)")
    return False


def validate(units, section_order, structure_notes, spec, manifest=None,
             qc_note_present=False):
    rep = Report()
    spec_by_id = {s["id"]: s for s in spec["sections"]}
    sequence = spec["sequence"]
    child_ids = set()
    for parent, cs in spec.get("containment", {}).get("child_sections", {}).items():
        child_ids.update(cs.get("ids", []))

    for note in structure_notes:
        rep.fails.append(f"structure: {note}")

    # --- sequence, presence, extras -------------------------------------
    for sid in section_order:
        if sid in child_ids:
            rep.fails.append(
                f"structure: Section {sid} is a child of its parent section, "
                f"not a standalone section (containment model)")
        elif sid not in spec_by_id:
            rep.fails.append(
                f"structure: Section {sid} is not in the {spec['copy_version']} "
                f"sequence {sequence}; extra sections fail")
    present = [s for s in section_order if s in spec_by_id]
    for sid in sequence:
        if spec_by_id[sid].get("required", True) and sid not in present:
            rep.fails.append(f"structure: required section {sid} "
                             f"({spec_by_id[sid]['framework_name']}) is missing")
    if present and present != [s for s in sequence if s in present]:
        rep.fails.append(
            f"structure: sections are out of order; found {present}, "
            f"the spec order is {sequence}")

    by_section = {}
    for u in units:
        by_section.setdefault(u.section, []).append(u)

    failed_keys_by_section = {}

    # --- per-section limits, element counts, CTA, steps, parts ----------
    for sid in sequence:
        sspec = spec_by_id[sid]
        sunits = by_section.get(sid, [])
        rep.counts[sid] = {"words": count_words(sunits),
                            "chars": count_chars(sunits)}
        if sid not in present:
            continue
        failed_keys = failed_keys_by_section.setdefault(sid, set())
        label = f"Section {sid} ({sspec['framework_name']})"

        for lim in sspec.get("limits", []):
            if lim.get("scope") in ("section", "family"):
                value = measure(sunits, lim["unit"])
                check_limit(rep, value, lim, label, failed_keys)

        # Dual-band sections (Long-Form Section 7): accept either declared band.
        wb = sspec.get("word_bands")
        if wb:
            w = count_words(sunits)
            matched = None
            for band in wb["bands"]:
                if band["min"] <= w <= band["max"]:
                    matched = band["id"]
                    break
            if matched:
                rep.infos.append(f"{label}: {w} words matches the "
                                 f"'{matched}' band")
                rep.counts[sid]["band"] = matched
            else:
                names = "; ".join(f"{b['id']} {b['min']}-{b['max']}"
                                  for b in wb["bands"])
                rep.warns.append(
                    f"{label}: {w} words matches neither declared band ({names})")

        for ec in sspec.get("element_counts", []):
            found = [u for u in sunits if u.kind == ec["unit_kind"]]
            if not found:
                rep.flags.append(
                    f"{label}: no {ec['unit_kind']} entries found, so the "
                    f"{ec['element']} count ({ec['min']}-{ec['max']}) could not "
                    f"be verified mechanically; reviewer confirms")
            else:
                lim = {"unit": "entries", "min": ec["min"], "max": ec["max"],
                       "kind": ec.get("kind", "hard"), "scope": "count",
                       "source": ec.get("source", "")}
                check_limit(rep, len(found), lim,
                            f"{label} {ec['element']}", failed_keys)

        # CTA map per section.
        buttons = [u for u in sunits if u.kind == "cta_button"]
        cta = sspec.get("cta", {})
        cta_map = spec.get("cta_map", {})
        if cta.get("standalone") == "required":
            if not buttons:
                rep.fails.append(
                    f"CTA map: {label} must carry a standalone CTA module; "
                    f"none found (required positions: "
                    f"{', '.join(cta_map.get('required_in_sections', []))})")
            elif len(buttons) > 1:
                rep.fails.append(
                    f"CTA map: {label} carries {len(buttons)} standalone CTA "
                    f"buttons; the map allows exactly one module at this position")
        elif cta.get("standalone") == "forbidden":
            if buttons:
                rep.fails.append(
                    f"CTA map: {label} carries a standalone CTA button, which "
                    f"this version forbids here (forbidden positions: "
                    f"{', '.join(cta_map.get('forbidden_in_sections', []))})")
        # Section 5 family: the single module must not sit inside an early child.
        if sid == "5" and buttons:
            children_present = []
            for u in sunits:
                if u.child and u.child not in children_present:
                    children_present.append(u.child)
            if children_present:
                last_child = children_present[-1]
                for b in buttons:
                    if b.child is not None and b.child != last_child:
                        rep.fails.append(
                            f"CTA map: Section 5's standalone CTA sits inside "
                            f"child {b.child}; the single family module belongs "
                            f"after the family's final child ({last_child}), "
                            f"never one per panel")

        # Steps (Section 11).
        sr = sspec.get("step_rules")
        if sr:
            steps = [u for u in sunits if u.kind == "step"]
            sc = sr.get("step_count")
            if sc:
                if not steps:
                    rep.flags.append(
                        f"{label}: no numbered steps found, so the step count "
                        f"could not be verified mechanically; reviewer confirms")
                else:
                    lim = {"unit": "steps", "min": sc["min"], "max": sc["max"],
                           "kind": sc.get("kind", "hard"), "scope": "count",
                           "source": sc.get("source", "")}
                    check_limit(rep, len(steps), lim, f"{label} step count",
                                failed_keys)
            ps = sr.get("per_step_chars")
            if ps and ps.get("applies", True) and steps:
                want = ps.get("applies_when_step_count")
                if want is not None and len(steps) != want:
                    rep.infos.append(
                        f"{label}: per-step character bands are undefined for "
                        f"{len(steps)} steps by the guide (defined only for "
                        f"{want}); an explicit allocation decision is required "
                        f"(spec: other_step_counts = "
                        f"{ps.get('other_step_counts')})")
                elif want is not None:
                    for i, st in enumerate(steps, 1):
                        c = len(st.text)
                        if i < len(steps):
                            band = ps["steps_1_to_6"]
                            loc = f"Step {i}"
                        else:
                            band = ps["step_7"]
                            loc = f"Step {i}"
                        lim = {"unit": "chars", "min": band.get("min"),
                               "max": band.get("max"),
                               "kind": band.get("kind", "hard"),
                               "scope": "step", "source": ps.get("source", "")}
                        check_limit(rep, c, lim, f"{label} {loc}", failed_keys)

    # --- standalone CTA total ---------------------------------------------
    cta_map = spec.get("cta_map", {})
    total_rule = cta_map.get("standalone_total")
    if total_rule:
        total = sum(1 for u in units if u.kind == "cta_button")
        rep.counts["_cta_total"] = {"buttons": total}
        if total != total_rule["value"]:
            rep.fails.append(
                f"CTA map: manuscript carries {total} standalone CTA buttons; "
                f"this version's map requires exactly {total_rule['value']} "
                f"(positions: {', '.join(cta_map.get('required_in_sections', []))})")

    # --- founder letter parts ----------------------------------------------
    letter = spec.get("founder_letter")
    if letter and letter["section"] in present:
        sid = letter["section"]
        sunits = by_section.get(sid, [])
        parts_found = []
        for u in sunits:
            if u.part is not None and (not parts_found or parts_found[-1] != u.part):
                parts_found.append(u.part)
        for pspec in letter["parts"]:
            n = pspec["n"]
            punits = [u for u in sunits if u.part == n]
            rep.counts.setdefault(sid, {})[f"part_{n}_words"] = count_words(punits)
            if not punits:
                rep.fails.append(
                    f"Founder letter: Part {n} ({pspec['label']}) is missing "
                    f"from Section {sid}; all six internal parts are required")
                continue
            fk = failed_keys_by_section.setdefault(sid, set())
            for lim in pspec.get("limits", []):
                value = measure(punits, lim["unit"])
                check_limit(rep, value, lim,
                            f"Founder letter Part {n} ({pspec['label']})", fk)
        expected_order = [p["n"] for p in letter["parts"]]
        seen = [n for n in expected_order if n in parts_found]
        if parts_found and seen != parts_found:
            rep.fails.append(
                f"Founder letter: parts appear out of order ({parts_found}); "
                f"required order is {expected_order}")

    # --- whole-page band (target-level; compact path only) -----------------
    wp = spec.get("whole_page")
    if wp:
        s7_band = rep.counts.get("7", {}).get("band", "compact")
        if s7_band == "compact":
            total_words = sum(count_words(by_section.get(s, []))
                              for s in sequence)
            rep.counts["_page_words"] = {"words": total_words}
            fk = set()
            check_limit(rep, total_words,
                        {"unit": "words", "min": wp["min"], "max": wp["max"],
                         "kind": wp.get("kind", "target"), "scope": "page",
                         "source": wp.get("source", "")},
                        "Whole page (compact-What path)", fk)

    # --- qualitative prefilters (FLAGs, never failures) ---------------------
    rules = {r["id"]: r for r in spec.get("qualitative_rules", [])}
    for sspec in spec["sections"]:
        sid = sspec["id"]
        if sid not in present:
            continue
        sunits = by_section.get(sid, [])
        for flag_id in sspec.get("flags", []):
            rule = rules.get(flag_id, {})
            if flag_id == "no_question_led_pain":
                for u in sunits:
                    if u.kind in ("para", "bullet") and "?" in u.text:
                        rep.flags.append(
                            f"Section {sid}: question sentence flagged for "
                            f"rule '{flag_id}' (the guide bans question-led "
                            f"pain framing; reviewer confirms): "
                            f"\"{u.text[:80]}\"")
                        break
            elif flag_id == "why_opener":
                first = next((u for u in sunits if u.kind == "para"), None)
                prefixes = rule.get("accepted_prefixes", [])
                if first is not None and prefixes and not any(
                        first.text.startswith(p) for p in prefixes):
                    rep.flags.append(
                        f"Section {sid}: opening does not start with "
                        f"{' / '.join(repr(p) for p in prefixes)}; flagged "
                        f"for rule '{flag_id}' (a natural equivalent is the "
                        f"reviewer's call): \"{first.text[:80]}\"")

    invite = rules.get("invite_names_offer")
    if invite and manifest and manifest.get("offer_name"):
        name = str(manifest["offer_name"])
        s1_text = " ".join(u.text for u in by_section.get("1", []))
        p5_text = " ".join(u.text for u in by_section.get("12", [])
                           if u.part == 5)
        if name.lower() not in s1_text.lower():
            rep.flags.append(
                f"Offer name '{name}' from the copy manifest was not found in "
                f"Section 1 (prefilter for rule 'invite_names_offer')")
        elif p5_text and name.lower() not in p5_text.lower():
            rep.flags.append(
                f"Section 12 Part 5 (The Big Invite) does not name the offer "
                f"'{name}' that Section 1 names (prefilter for rule "
                f"'invite_names_offer'; reviewer confirms)")

    # --- deviation-note requirement for out-of-band target sections --------
    plaw = spec.get("procedural_law", {})
    if plaw.get("deviation_note_required") and rep.warns and not qc_note_present:
        rep.warns.append(
            "Procedural law: sections outside their suggested bands require "
            "a material-allocation note in the non-public QC note instead of "
            "padding (spec procedural_law.deviation_note_required); none was "
            "found in the copy manifest or a copy/qc-note.md file")

    return rep


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def load_spec(path):
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read spec {path}: {exc}")
        sys.exit(2)
    for key in ("copy_version", "sequence", "sections", "counting_convention"):
        if key not in spec:
            print(f"FAIL: spec {path} is missing required key '{key}'")
            sys.exit(2)
    return spec


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate a copy manuscript against a copy spec "
                    "(Item 18; counts in the spec's own units).")
    parser.add_argument("target",
                        help="a run directory (uses copy/internal-manuscript.md "
                             "and copy/copy-manifest.json) or a manuscript .md file")
    parser.add_argument("--spec", required=True,
                        help="path to the copy spec JSON (references/copy-specs/)")
    parser.add_argument("--manifest",
                        help="path to copy-manifest.json (defaults to the one "
                             "in the run directory, if any)")
    parser.add_argument("--json", action="store_true",
                        help="print the full report as JSON")
    args = parser.parse_args(argv)

    spec = load_spec(args.spec)
    target = Path(args.target)
    manifest = None
    qc_note_present = False
    if target.is_dir():
        manuscript_path = target / "copy" / "internal-manuscript.md"
        manifest_path = Path(args.manifest) if args.manifest else \
            target / "copy" / "copy-manifest.json"
        qc_note_present = (target / "copy" / "qc-note.md").exists()
    else:
        manuscript_path = target
        manifest_path = Path(args.manifest) if args.manifest else None
    try:
        text = manuscript_path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"FAIL: could not read manuscript {manuscript_path}: {exc}")
        return 2
    if manifest_path is not None and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"FAIL: could not read manifest {manifest_path}: {exc}")
            return 2
    if isinstance(manifest, dict) and manifest.get("deviation_notes"):
        qc_note_present = True
    if isinstance(manifest, dict) and manifest.get("copy_version") and \
            manifest["copy_version"] != spec["copy_version"]:
        print(f"WARN: copy manifest declares copy_version "
              f"'{manifest['copy_version']}' but the spec is "
              f"'{spec['copy_version']}'; validating against the spec given")

    units, section_order, structure_notes = parse_manuscript(text)
    rep = validate(units, section_order, structure_notes, spec,
                   manifest=manifest, qc_note_present=qc_note_present)

    if args.json:
        out = {"spec": spec["spec_id"], "copy_version": spec["copy_version"],
               "counts": rep.counts, "fails": rep.fails, "warns": rep.warns,
               "flags": rep.flags, "infos": rep.infos,
               "result": "FAIL" if rep.fails else "PASS"}
        print(json.dumps(out, indent=1))
    else:
        print(f"Copy structure validation (spec: {spec['spec_id']}, "
              f"{spec['copy_version']})")
        names = {s["id"]: s["framework_name"] for s in spec["sections"]}
        for sid in spec["sequence"]:
            c = rep.counts.get(sid)
            if c:
                extra = f" (band: {c['band']})" if "band" in c else ""
                print(f"  Section {sid} ({names[sid]}): words={c['words']} "
                      f"chars={c['chars']}{extra}")
        for line in rep.fails:
            print(f"FAIL: {line}")
        for line in rep.warns:
            print(f"WARN: {line}")
        for line in rep.flags:
            print(f"FLAG: {line}")
        for line in rep.infos:
            print(f"INFO: {line}")
        result = "FAIL" if rep.fails else "PASS"
        print(f"RESULT: {result} ({len(rep.fails)} failures, "
              f"{len(rep.warns)} warnings, {len(rep.flags)} flags)")
    return 1 if rep.fails else 0


if __name__ == "__main__":
    sys.exit(main())
