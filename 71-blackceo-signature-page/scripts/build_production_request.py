#!/usr/bin/env python3
"""Build a stage's production-request.json from the run's copy manuscript.

The request is the input of scripts/stage_executor.py. This builder is the
skill's own path from the copy to that request, and it makes one rule
structural: ONE request section per canonical copy section of the selected
form, never band-compressed. Standard has 12 (references/copy-specs/
standard-v6.json `sequence`); Long-Form has 15 (long-form-v6.json `sequence`:
1, 2, 2A, 3, 3A, 4, 4A, 5, 6, 7, 8, 9, 10, 11, 12). Every stage therefore
renders one image per section, per platform.

Fail-closed: a manuscript that does not carry exactly the form's sections in
order is refused, and the finished request must pass the same
check_section_count the executor runs before it is written. Zero provider
calls; the file is the only output.

Usage:
  build_production_request.py --copy-version standard|long-form \\
      --manuscript <run_dir>/copy/internal-manuscript.md --stage visual-mockup \\
      --out <run_dir>/production-request.json [--slots slots.json] \\
      [--design-prose prose.json] [--references a.png,b.png] [--model ID] [--style TEXT]

  slots.json:  {"<canonical section id>": [{"slot_id", "aspect_ratio", "art_direction"}]}
  prose.json:  {"notes": str, "traits": str, "rules_md": str, "rules_json": str}
               optional design prose, added in that priority order while every
               section's composed prompt stays at or under the model's 95 percent
               target; copy and contract blocks are never cut.

Exit codes: 0 written; 1 named refusal; 2 usage.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stage_executor as exe  # noqa: E402
from validate_copy_structure import parse_manuscript  # noqa: E402

LEADS = {
    "desktop-wireframe": "Desktop wireframe sheet, section {section_number} of {section_total}, "
                         "{section_name}, at {width}px.",
    "mobile-tablet": "Mobile wireframe sheet, section {section_number} of {section_total}, "
                     "{section_name}, at {width}px.",
    "visual-mockup": "Styled desktop and mobile mockup, section {section_number} of "
                     "{section_total}, {section_name}, at {width}px.",
    "final-mockups": "Final production mockup, section {section_number} of {section_total}, "
                     "{section_name}, at {width}px. Photographic editorial finish.",
}
BLOCKS = (("notes", "LAYOUT NOTES"), ("traits", "VISUAL STANDARD TRAITS"),
          ("rules_md", "DESIGN SYSTEM, MEASURED"), ("rules_json", "DESIGN TOKENS"))
MD_BLOCKS = ("notes", "traits", "rules_md")
SECTION_TAIL = ("SECTION {section_number} of {section_total}: {section_name} at {width}px\n"
                "{layout}\nLAYOUT AND COPY:\n{copy}\nIMAGE SLOTS:\n{slots}")


# Neutral role names for the wireframe annotation. The guide's framework labels
# ("Big Bold Pain 1", "2A") are private and must never reach a public mockup.
ROLE_NAMES = {
    "1": "Opening claim", "2": "First problem", "2A": "First solution",
    "3": "Second problem", "3A": "Second solution", "4": "Third problem",
    "4A": "Third solution", "5": "Why", "6": "Who it is for", "7": "What you get",
    "8": "First benefit", "9": "Second benefit", "10": "Third benefit",
    "11": "Steps", "12": "Founder letter",
}


# Genuine per-section specification. The shared design prose is the client's
# measured system and fills most of the band; what is left is topped up, per
# section, from the skill's own references (the skeleton table of
# references/section-image-prompt.md, the copy spec) and the section's own copy.
# Nothing here repeats the copy block, and nothing is added once a section is
# at the band ceiling (padding is a validator failure).
SKELETON_DOC = exe.SKILL_ROOT / "references" / "section-image-prompt.md"
ROW = re.compile(r"^\|\s*(\d+[A-C]?)\s*\|[^|]*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", re.M)
PRIVATE_ID = re.compile(r"\b[2-5][A-C]\b\s*")
# The guide's internal vocabulary must never reach a prompt (see ROLE_NAMES).
PRIVATE_TEXT = re.compile(r"\bSection \d+[A-C]\b|\bP0\d\b|\b[2-5][A-C]\b|\bPart [A-Z]\b|Big Bold|"
                          r"framework|CTA BUTTON|CTA MICROCOPY|\bPain \d|\bSolution \d", re.I)
ORDINAL = ("first", "second", "third")

COMMON_CANON = [
    "FRAME AND MEASURE: the desktop page is 1440 px wide with a 1200 px content column; "
    "the mobile page is 390 CSS px wide with a 342 px content column, exported at 2x "
    "(780 px). The slice keeps its own native height and is the pixel-mate of the same "
    "section on the other platform: same band order, same copy, same slots, only the "
    "layout adapts. 3:1, 1:3 and 9:21 are not offered ratios, so the nearest offered "
    "ratio is used.",
    "TYPE SCALE: headline 48 to 64 px on desktop and 34 to 48 px on mobile; subhead 28 "
    "to 36 px; body 18 to 20 px on desktop and 15 to 17 px on mobile; button label 18 "
    "to 20 px; microcopy 12 to 14 px on desktop and 12 to 13 px on mobile; the eyebrow "
    "sits above the headline in tracked capitals. Measured values in the design system "
    "above override these canon sizes wherever the two differ.",
    "READABILITY: every printed word must stay legible at the delivered pixel width. "
    "Letters never merge, clip, mirror or slant into the next word; no word breaks "
    "mid-word; body lines run 45 to 75 characters; headline lines break at a phrase, "
    "never on a single orphaned word; contrast between text and its ground stays high "
    "enough to read at a glance on a phone held at arm's length.",
    "SPELLING AND NUMBERS: each printed string is copied character for character from "
    "the verbatim block. Numerals, times, currency and hyphenated words keep their "
    "written form; apostrophes and quotation marks keep their typographic shape. A "
    "region with no copy stays quiet space or a designed image, and is never filled "
    "with extra words.",
]
STAGE_CANON = {
    "desktop-wireframe": [
        "WIREFRAME PURPOSE: this is a designed, annotated build spec rendered as an "
        "image, in the client's brand colours, never a plain grey browser render. A "
        "developer reading only this slice can build the section.",
        "ANNOTATIONS: print the section number and name once; a header strip stating "
        "page width and content width; the type spec (family, size, weight) beside "
        "each text element; the real copy; behaviour notes where they govern rather "
        "than in a legend.",
        "SLOT DRAWING: each image slot is a deliberate placeholder labelled with its "
        "ratio and its art direction, and the ratio label matches the rectangle drawn. "
        "Photographic plates are darkened with a thin accent edge bar.",
        "BUTTON CHIP: a button appears as a designed chip carrying the real label, with "
        "its microcopy spec beside it; a section without a button prints no chip.",
    ],
    "mobile-tablet": [
        "WIREFRAME PURPOSE: this is a designed, annotated mobile build spec rendered as "
        "an image, in the client's brand colours, at 390 px. A developer reading only "
        "this slice can build the section.",
        "ANNOTATIONS: print the section number and name once; a header strip stating "
        "page width and content width; the type spec beside each text element; the real "
        "copy; mobile-specific behaviour printed on the section it governs.",
        "STACKING: columns collapse to one; the image slot keeps its labelled ratio and "
        "sits where the stacking note says; the button spans the content column.",
        "BUTTON CHIP: a button appears as a full-width designed chip carrying the real "
        "label, with its microcopy spec under it; a section without a button prints no "
        "chip.",
    ],
    "visual-mockup": [
        "MOCKUP PURPOSE: the same page as the wireframe with nothing left as a "
        "placeholder. Real copy, filled brand-colour buttons, and real colour imagery "
        "built to each slot's art direction, drawn so the slice reads like a screenshot "
        "of the finished page.",
        "PIXEL-MATE: band count, order, column structure and slot positions match the "
        "wireframe; only colour, photography and finish change.",
        "IMAGERY: each slot carries a real subject, ratio, casting and art direction; "
        "the founder slot stays the planned portrait or the supplied asset; no slot is "
        "drawn as a crossed box.",
        "BUTTONS AND ACCENTS: buttons are solid brand-colour fills with the real label "
        "and the microcopy line directly under them; accent rules and script overlays "
        "follow the design system above.",
    ],
    "final-mockups": [
        "FINISH PURPOSE: the final production mockup the client judges. It repeats the "
        "approved copy and layout exactly, and raises only the finish: photographic "
        "editorial quality and crisp type.",
        "PHOTOGRAPHY: natural skin texture, believable hands and fabric, consistent "
        "lighting direction inside one image; no plastic "
        "smoothing, no warped fingers, no duplicated limbs.",
        "TYPOGRAPHY AS IMAGE: headlines and buttons are sharp vector-clean letterforms; "
        "small text keeps its weight and spacing instead of smearing into texture.",
        "CONTINUITY: the slice joins the sections above and below it edge to edge, so "
        "the top and bottom ground colours match the neighbouring slices and no seam, "
        "border or gap shows.",
    ],
}
STAGE_CHECK = {
    "desktop-wireframe": "SELF-CHECK before finishing: the section number prints once; every word of the verbatim "
                         "block prints and nothing else does; each slot shows its ratio and art direction; the "
                         "type specs match the printed elements; no real photograph replaces a placeholder.",
    "mobile-tablet": "SELF-CHECK before finishing: the section number prints once; every word of the verbatim "
                     "block prints and nothing else does; the stacking order is one column; the button, when "
                     "there is one, spans the content column; no desktop-width layout survives.",
    "visual-mockup": "SELF-CHECK before finishing: every word of the verbatim block prints and nothing else does; "
                     "no slot is a placeholder; the button label is spelled exactly; the layout matches the "
                     "wireframe band.",
    "final-mockups": "SELF-CHECK before finishing: every word of the verbatim block prints and nothing else does; "
                     "faces, hands and fabric hold up at full size; small text is crisp; the button label is "
                     "spelled exactly; the slice would sit flush against its neighbours.",
}
KIND_ROLE = {
    "headline": "the largest text on the slice, two-tone statement-turn when it has a turn",
    "short": "a label, subhead or chip line, set smaller than the headline and larger than body",
    "body": "a paragraph in sentence case, left aligned, never wider than the content column",
    "step": "a numbered step whose badge number prints once, in order",
}


def neutral(text):
    """The guide's "Pain 2" is the page's "second cost": same job, no framework name."""
    return re.sub(r"\bpain 0?([1-3])\b", lambda m: f"the {ORDINAL[int(m.group(1)) - 1]} cost", text or "", flags=re.I)


def skeleton_table():
    out = {}
    for sid, purpose, slots in ROW.findall(SKELETON_DOC.read_text(encoding="utf-8")):
        out[sid] = {"purpose": purpose, "slots": slots}
    for row in out.values():  # "Same slots as 8" points at another row of the table
        ref = re.match(r"Same slots as (\w+)", row["slots"])
        if ref and ref.group(1) in out:
            row["slots"] = out[ref.group(1)]["slots"]
        row["slots"] = PRIVATE_ID.sub("", row["slots"])
    return out


def line_role(line, first):
    if re.match(r"\d+\.\s", line):
        return "step"
    if first:
        return "headline"
    if len(line.split()) <= 12:
        return "short"
    return "body"


def limits_phrase(spec_section):
    """One planned range per unit; a target beats a hard limit."""
    best = {}
    for l in spec_section.get("limits", []):
        if l.get("max") and l.get("kind") != "descriptive" and (l["unit"] not in best or l["kind"] == "target"):
            best[l["unit"]] = f"{str(l['min']) + ' to ' if l.get('min') else 'up to '}{l['max']} {l['unit']}"
    return "; ".join(best.values())


def fit_estimate(role, text):
    """Rough line counts at the canon type scale (average glyph = half the font size)."""
    desktop_px, mobile_px = {"headline": (56, 40), "short": (30, 24)}.get(role, (19, 16))
    per_line = lambda content, px: max(1, min(75, int(content / (px * 0.5))))
    lines = lambda content, px: -(-len(text) // per_line(content, px))
    return lines(1200, desktop_px), lines(342, mobile_px)


def section_fragments(stage, section, index, sections, spec, table):
    """Ordered specification paragraphs for one section; each is added only while it fits."""
    sid = exe.canon_section_id(section["section_id"])
    n = len(sections)
    names = [s["section_name"] for s in sections]
    spec_section = next((x for x in spec["sections"] if exe.canon_section_id(x["id"]) == sid), {})
    row = table.get(sid, {})
    lines = [l for l in str(section.get("copy") or "").splitlines() if l.strip()]
    roles = [line_role(l, i == 0) for i, l in enumerate(lines)]
    out = []
    near = [f"directly below {names[index - 2]}" if index > 1 else "at the top of the page, under the header",
            f"directly above {names[index]}" if index < n else "the last section before the footer"]
    out.append(f"SECTION SPECIFICATION: this slice is section {index} of {n}, {section['section_name']}, "
               f"{near[0]} and {near[1]}. Draw this section only.")
    purpose = [x.rstrip(".") for x in map(neutral, (row.get("purpose"), spec_section.get("job")))
               if x and not PRIVATE_TEXT.search(x)]
    if purpose:
        out.append("PURPOSE: " + "; ".join(purpose) + ".")
    # first, so the run's planned slots win the budget the new contract blocks left
    if row.get("slots") and section.get("slots"):  # the run's IMAGE SLOTS list governs; no plan, no canon
        out.append("SLOT CANON: the usual slots for this kind of section are " + row["slots"].rstrip(".") +
                   ". Each planned slot keeps its stated ratio and is drawn once.")
    out.append("PAGE ORDER: " + ", ".join(f"{i}. {name}" for i, name in enumerate(names, 1)) +
               ". The numbered sections never merge and never renumber.")
    if lines:
        count = {k: roles.count(k) for k in dict.fromkeys(roles)}
        words = sum(len(l.split()) for l in lines)
        vol = limits_phrase(spec_section)
        out.append("COPY ANATOMY: " + ", ".join(f"{v} x {k}" for k, v in count.items()) +
                   f"; {words} printed words in all" + (f" (the form plans {vol} for this section)" if vol else "") +
                   ". Size and space the text so all of it prints at a readable size.")
    cta = exe._cta_label(section.get("cta"))
    forbidden = {exe.canon_section_id(x) for x in (spec.get("cta_map", {}).get("forbidden_in_sections") or [])}
    if cta:
        out.append(f'BUTTON: this section carries exactly one button, labelled "{cta}", with the microcopy '
                   "line under it when the copy block supplies one; no second button, link row or sticky bar.")
    elif sid in forbidden:
        out.append("BUTTON: this section carries no button, no chip and no button-shaped pill; a button here is a defect.")
    else:
        out.append("BUTTON: none planned; draw a button only if the copy block above prints a label for it.")
    out.extend(COMMON_CANON[:1])
    out.extend(STAGE_CANON[stage][:2])
    if lines:
        out.append("TYPE ROLES: " + "; ".join(f"the {k} is {KIND_ROLE[k]}" for k in dict.fromkeys(roles)) + ".")
    plan, fit = [], {}
    for i, (line, role) in enumerate(zip(lines, roles), 1):
        d, m = fit_estimate(role, line)
        fit[role] = [fit.get(role, [0, 0])[0] + d, fit.get(role, [0, 0])[1] + m]
        plan.append(f"{i} {role} opening \"{' '.join(line.split()[:4])}\" ({len(line.split())} words)")
    for k in range(0, len(plan), 3):  # three lines per paragraph keeps the top-up granular
        out.append(f"LINE PLAN {k + 1} to {min(k + 3, len(plan))}: " + "; ".join(plan[k:k + 3]) + ".")
    if fit:
        out.append("TEXT FIT, estimated rendered lines as desktop / mobile: " +
                   "; ".join(f"{role} {d} / {m}" for role, (d, m) in fit.items()) +
                   ". Leave room for them; never shrink type below the canon scale to fit.")
    out.extend(STAGE_CANON[stage][2:])
    out.extend(COMMON_CANON[1:])
    out.append("READING ORDER: the eye enters at the headline, passes the image slot when there is one, and "
               "ends at the button or the bottom edge. Desktop reads left to right inside the 1200 px column; "
               "mobile reads top to bottom, with an image slot following the headline unless the design "
               "system above places it elsewhere.")
    out.append("CONTINUITY: the top edge continues the ground of the slice above and the bottom edge hands "
               "off to the slice below; when the neighbouring bands differ in tone, the change happens "
               "exactly at the slice edge, never inside it, and no seam, border or gap shows.")
    out.append(STAGE_CHECK[stage])
    return out


def padding_check(request, stage):
    """Fail closed on the validator's own padding screens (repetition is not specification)."""
    from validate_prompt import padding_errors
    for index, section in enumerate(request["sections"], start=1):
        with contextlib.redirect_stderr(io.StringIO()):
            prompt = exe.stage_prompt(stage, section, index, exe.LAYOUT[stage][0][1], request, "3:4")
        errors = padding_errors(prompt.strip(), re.findall(r"\S+", prompt))
        if errors:
            raise BuildError(f"section {section['section_id']}: {errors[0]}")


def worst_size(request, stage, index, section):
    worst = 0
    for _tpl, width, _h in exe.LAYOUT[stage]:
        with contextlib.redirect_stderr(io.StringIO()):
            worst = max(worst, len(exe.stage_prompt(stage, section, index, width, request, "3:4")))
    return worst


def fill_to_band(request, stage, spec):
    """Top each section's `layout` up with genuine specification, toward the band ceiling.

    The ceiling is midway between the 95 percent target and the model maximum, so a
    prompt lands inside the 95 to 100 percent band with room for width variance. A
    section is never pushed over the maximum and never padded with repetition.
    """
    budget = exe.prompt_budget(request.get("model"))
    if not budget:
        return
    ceiling = (budget["target_chars"] + budget["max_chars"]) // 2
    table = skeleton_table()
    for index, section in enumerate(request["sections"], start=1):
        parts = [str(section.get("layout") or "").strip()]
        parts = [p for p in parts if p]
        for text in section_fragments(stage, section, index, request["sections"], spec, table):
            if PRIVATE_TEXT.search(text):
                continue
            section["layout"] = "\n".join(parts + [text])
            if worst_size(request, stage, index, section) <= ceiling:
                parts.append(text)
        section["layout"] = "\n".join(parts)


class BuildError(Exception):
    pass


def section_copy(units):
    """Public copy lines of one section, and its single CTA button label."""
    lines, buttons = [], []
    for u in units:
        if u.kind == "cta_button":
            buttons.append(u.text)
        elif u.kind == "step":
            lines.append(f"{u.step_no}. {u.text}")
        else:
            lines.append(u.text)
    return "\n".join(lines), buttons


def sections_from_manuscript(text: str, spec: dict, slots: dict) -> list:
    units, order, _notes = parse_manuscript(text)
    sequence = list(spec["sequence"])
    if order != sequence:
        raise BuildError(
            f"section count: the manuscript has {len(order)} sections {order} but the "
            f"{spec['copy_version']} copy has {len(sequence)} canonical sections {sequence}; "
            f"missing {[i for i in sequence if i not in order]}, unexpected "
            f"{[i for i in order if i not in sequence]}")
    out = []
    for sid in sequence:
        copy, buttons = section_copy([u for u in units if u.section == sid])
        if len(buttons) > 1:
            raise BuildError(f"section {sid}: {len(buttons)} CTA buttons {buttons}; "
                             "one button per section")
        entry = {"section_id": sid, "section_name": ROLE_NAMES[sid], "copy": copy,
                 "cta": buttons[0] if buttons else None, "slots": slots.get(sid, [])}
        # The founder letter ends with the founder's signature (copy spec, Section 12
        # Part 6): a name, not a sentence. It is a verbatim label of its own so the
        # executor's truncated-copy guard keeps reading prose only.
        rows = copy.splitlines()
        if sid == "12" and len(rows) > 1 and rows[-1][-1] not in exe.TERMINAL and len(rows[-1].split()) <= 8:
            entry["copy"], entry["labels"] = "\n".join(rows[:-1]), [rows[-1]]
        out.append(entry)
    return out


def template_for(stage: str, blocks: dict) -> str:
    parts = [LEADS[stage]]
    for key, heading in BLOCKS:
        if blocks.get(key):
            body = blocks[key]
            if key == "rules_json":  # literal braces survive the wire's str.format
                body = body.replace("{", "{{").replace("}", "}}")
            parts += [heading, body]
    parts.append(SECTION_TAIL)
    return "\n\n".join(parts)


def sizes_for(request: dict, stage: str, quiet: bool = False, strict: bool = False):
    out = {}
    for index, section in enumerate(request["sections"], start=1):
        worst = 0
        for _tpl, width, _h in exe.LAYOUT[stage]:
            with contextlib.redirect_stderr(io.StringIO() if quiet else sys.stderr):
                prompt = exe.stage_prompt(stage, section, index, width, request, "3:4",
                                          strict_floor=strict)
            worst = max(worst, len(prompt))
        out[section["section_id"]] = worst
    return out


def run_blocks(request, run_dir):
    """Give the request what load_request gives the executor (the run's resolved client palette,
    page color system roles and design style), so every size measured here includes the blocks the
    executor adds. No palette means no honest size: refuse by name, never size without them."""
    request["_brand_block"] = exe.require_brand_colors(Path(run_dir))
    request["_hypersat"] = exe.hypersaturation.roles_for_run(run_dir)
    exe.resolve_design_style(Path(run_dir), request)


def build(stage, version, manuscript_text, slots, prose, references, model, style, run_dir=Path(".")):
    spec = json.loads((exe.SPEC_DIR / f"{version}-v6.json").read_text(encoding="utf-8"))
    sections = sections_from_manuscript(manuscript_text, spec, slots)
    prose = json.loads(neutral(json.dumps(prose)))  # a reference's "Pain 01" band label is a framework name too
    request = {"model": model, "style": style, "copy_version": version,
               "references": references, "sections": sections,
               "stage_prompts": {stage: template_for(stage, {})}}
    run_blocks(request, run_dir)
    budget = exe.prompt_budget(model)
    chosen = {}

    def fits(trial):
        request["stage_prompts"][stage] = template_for(stage, trial)
        try:
            return not budget or max(sizes_for(request, stage, quiet=True).values()) <= budget["target_chars"]
        except exe.ExecutorError:
            return False

    for key, _heading in BLOCKS:
        if not prose.get(key):
            continue
        text = prose[key]
        if key in MD_BLOCKS:
            # The palette lines (any #hex row) are superseded by the BRAND COLORS and PAGE COLOR
            # SYSTEM blocks the executor adds; the rest is trimmed from the tail, whole lines only,
            # until the worst section fits. Design prose gives way, never the verbatim copy.
            lines = [l for l in text.splitlines() if not exe.hypersaturation.ANY_HEX.search(l)]
            lo, hi = 0, len(lines)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if fits(dict(chosen, **{key: "\n".join(lines[:mid])})):
                    lo = mid
                else:
                    hi = mid - 1
            text = "\n".join(lines[:lo])
        if text and fits(dict(chosen, **{key: text})):
            chosen[key] = text
    request["stage_prompts"][stage] = template_for(stage, chosen)
    fill_to_band(request, stage, spec)
    try:  # raises by section name: copy alone over the maximum, or a section under the floor
        sizes = sizes_for(request, stage, strict=True)
    except exe.ExecutorError as exc:
        if "below the" in str(exc):
            raise BuildError(f"{exc} (supply --design-prose with the run's measured design system)")
        raise
    request["metadata"] = {
        "stage": stage, "copy_version": version, "section_count": len(sections),
        "canonical_ids": [s["section_id"] for s in sections], "provider_calls": 0,
        "dropped_blocks": [k for k, _h in BLOCKS if prose.get(k) and k not in chosen],
        "trimmed_blocks": [k for k in chosen if chosen[k] != prose[k]],
        "char_budget": {"target": budget and budget["target_chars"],
                        "max": budget and budget["max_chars"],
                        "min_seen": min(sizes.values()), "max_seen": max(sizes.values()),
                        "per_section": sizes},
    }
    padding_check(request, stage)
    # Fail closed on our own output, against the run this manuscript belongs to.
    request["metadata"]["checked_against"] = exe.check_section_count(run_dir, request, paid=True)[2]
    # The run's palette is re-resolved by the executor; it is never written into the request.
    for key in ("_brand_block", "_hypersat"):
        request.pop(key, None)
    return request


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--copy-version", choices=["standard", "long-form"], required=True)
    p.add_argument("--manuscript", type=Path, required=True)
    p.add_argument("--stage", choices=list(exe.STAGES), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--slots", type=Path)
    p.add_argument("--design-prose", type=Path)
    p.add_argument("--references", default="")
    p.add_argument("--model", default="gpt-image-2-5-sunburst-image-to-image")
    p.add_argument("--style", default="")
    p.add_argument("--run-dir", type=Path,
                   help="the run whose copy source and copy/copy-manifest.json the request is "
                        "checked against (default: the manuscript's run when it sits in "
                        "<run_dir>/copy/, else the folder of --out)")
    a = p.parse_args(argv)
    run_dir = a.run_dir or (a.manuscript.resolve().parent.parent
                            if a.manuscript.resolve().parent.name == "copy"
                            else a.out.resolve().parent)
    try:
        load = lambda f: json.loads(f.read_text(encoding="utf-8")) if f else {}
        request = build(a.stage, a.copy_version, a.manuscript.read_text(encoding="utf-8"),
                        load(a.slots), load(a.design_prose),
                        [r for r in a.references.split(",") if r], a.model, a.style, run_dir)
    except (BuildError, exe.ExecutorError, OSError, ValueError) as exc:
        print(f"REFUSED: {exc}")
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    m = request["metadata"]
    print(f"WROTE {a.out} copy_version={a.copy_version} stage={a.stage} "
          f"sections={m['section_count']} ids={','.join(m['canonical_ids'])}")
    cb = m["char_budget"]
    if cb["target"] and cb["min_seen"] < cb["target"]:  # floor passed (else refused); band goal missed
        print(f"WARN below the {cb['target']}-char target: shortest section {cb['min_seen']} chars; "
              "supply fuller --design-prose to reach the 95 to 100 percent band")
    print(f"CHECKED run_dir={run_dir} against={'; '.join(m['checked_against']) or 'request only'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
