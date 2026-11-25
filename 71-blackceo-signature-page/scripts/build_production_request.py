#!/usr/bin/env python3
"""Build a stage's production-request.json from the run's copy manuscript.

The request is the input of scripts/stage_executor.py. This builder is the
skill's own path from the copy to that request, and it makes one rule
structural: ONE request section per canonical copy section of the selected
form, never band-compressed. Standard has 12 (references/copy-specs/
standard-v6.json `sequence`); Long-Form has 15 (long-form-v6.json `sequence`:
1, 2, 2A, 3, 3A, 4, 4A, 5, 6, 7, 8, 9, 10, 11, 12); Product Selection (the order
page, Skill 78) has 5 (product-selection-v1.json). Every stage therefore
renders one image per section, per platform. A form's spec supplies its own
neutral section names, skeleton rows and per-section notes; nothing else differs.

A page type other than the landing page (the thank-you page) names its own canonical
sequence in its own copy spec (references/copy-specs/thank-you-v1.json, read through
scripts/page_role.py): the builder reads that spec the same way, seeds each section's
composition role, ground and default image slots from it, and stamps `page_role` into the
request, so every later stage draws that page's structure and never a landing page's.

Fail-closed: a manuscript that does not carry exactly the form's sections in
order is refused, and the finished request must pass the same
check_section_count the executor runs before it is written. Zero provider
calls; the file is the only output.

A page role with its own section sequence (references/copy-specs/roles/<role>.json,
checkout today) is built the same way: --page-role checkout selects that role's spec
instead of the landing form's, and --copy-version is then optional (the form label only
picks the style reference sheet). The role spec also supplies each section's name, its
default image slots, ground, composition role, behaviour note and desktop / mobile layout.

The upsell page (Skill 80, page roles upsell_1 and upsell_2) is its own form with 8
sections (references/copy-specs/upsell-v6.json). Its copy is Skill 80's validated JSON,
not a manuscript: pass --copy-json and --bundle (Skill 80's result bundle, whose
page_plan carries the exact amount-and-terms line and the order-confirmed lines) in
place of --manuscript.

Usage:
  build_production_request.py --copy-version upsell --page-role upsell_1 --copy-json copy-upsell_1.json \
      --bundle bundle-upsell_1.json --stage visual-mockup --out <run_dir>/production-request.json
  build_production_request.py [--page-role checkout] --copy-version standard|long-form \
      --manuscript <run_dir>/copy/internal-manuscript.md --stage visual-mockup \\
      --out <run_dir>/production-request.json [--page-kind sales|opt_in] [--slots slots.json] \\
      [--design-prose prose.json] [--references a.png,b.png] [--model ID] [--style TEXT] \
      [--style-card-id FN-001]
  build_production_request.py --copy-version product-selection|thank-you [--page-role that role] \
      --manuscript ... --stage ... --out ...   (omitted --page-role stamps the form's own role)

  Skill 45 (read-only, fix spec M4): every build reads the design library's prompt bands, negative-
  prompting rules and funnel page rules and writes <run_dir>/private/receipts/design-intelligence.json
  (the receipt stage_gate.py demands before image-inventory-prompts closes). When --style-card-id is
  given, or intake.json carries style_card_id, that card's LONG tier is embedded VERBATIM as a BRAND
  STYLE block in every section prompt; it is never trimmed, and a card too large for the model budget
  is a named refusal. A card or library file that cannot be read refuses with AF-DI-ABSENT.

  slots.json:  {"<canonical section id>": [{"slot_id", "aspect_ratio", "art_direction"}]}
  prose.json:  {"notes": str, "traits": str, "rules_md": str, "rules_json": str}
               optional design prose, added in that priority order while every
               section's composed prompt stays at or under the model's 95 percent
               target; copy and contract blocks are never cut.

A non-landing page role with an entry in references/page-structures.json is built
from that page's own copy document instead of a landing manuscript:

  build_production_request.py --page-role downsell_1 --page-copy <page.json> \
      --stage visual-mockup --out <run_dir>/production-request.json [--slots ...]

  The page copy is the role's owning-skill page object (for downsell_1, Skill 81's
  downsell-page schema). One request section per page section, in the entry's
  sequence; the same check_section_count the executor runs gates the result.

Exit codes: 0 written; 1 named refusal; 2 usage.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import copy_forms  # noqa: E402
import stage_executor as exe  # noqa: E402
import page_role  # noqa: E402  the one allowed-sequence resolver
from page_role import BUMP_SECTION  # noqa: E402  (build() has a `page_role` parameter of its own)
import role_spec  # noqa: E402
import wireframe_spec  # noqa: E402
import font_sizes  # noqa: E402  the closed font plan's sizes (SWB-400)
import section_plan  # noqa: E402  the closed image inventory's slots (SWB-400)
import page_kinds  # noqa: E402
from validate_copy_structure import parse_manuscript  # noqa: E402


def _load_design_intelligence():
    """shared-utils/signature_launch/design_intelligence.py, loaded by path (repo and installed layouts alike)."""
    import importlib.util
    path = HERE.parents[1] / "shared-utils" / "signature_launch" / "design_intelligence.py"
    spec = importlib.util.spec_from_file_location("signature_launch_design_intelligence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


di = _load_design_intelligence()

LEADS = {
    "desktop-wireframe": "Desktop wireframe sheet, section {section_number} of {section_total}, "
                         "{section_name}, at {width}px.",
    "mobile-tablet": "Mobile wireframe sheet, section {section_number} of {section_total}, "
                     "{section_name}, at {width}px.",
    "visual-mockup": "Styled desktop and mobile mockup, section {section_number} of "
                     "{section_total}, {section_name}, at {width}px.",
    "final-mockups": "Final production mockup, section {section_number} of {section_total}, "
                     "{section_name}, at {width}px. Photographic editorial finish. The attached "
                     "wireframe is a layout reference: its section chips, name tabs, type-spec "
                     "labels and behaviour notes are annotations and are never drawn.",
}
BLOCKS = (("notes", "LAYOUT NOTES"), ("traits", "VISUAL STANDARD TRAITS"),
          ("rules_md", "DESIGN SYSTEM, MEASURED"), ("rules_json", "DESIGN TOKENS"))
MD_BLOCKS = ("notes", "traits", "rules_md")
BRAND_STYLE_HEAD = "BRAND STYLE (design library style card, LONG tier, verbatim)"
SECTION_HEAD = "SECTION {section_number} of {section_total}: {section_name} at {width}px\n"
SECTION_BODY = "{layout}\nLAYOUT AND COPY:\n{copy}\nIMAGE SLOTS:\n{slots}"
SECTION_TAIL = SECTION_HEAD + SECTION_BODY
# A wireframe slice IS an annotated build spec, so its heading belongs in its prompt.
# A mockup is the finished page: the numbered chip, the name tab and the annotation
# blocks are production scaffolding and must never be drawn into it (see ROLE_NAMES,
# and the comment above it). Only the body is sent to the mockup stages.
MOCKUP_PROMPT_STAGES = ("visual-mockup", "final-mockups")


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
    "heading": "the section heading, set once in the display face at the second-largest size in the one "
               "text colour, never filled with an accent colour",
}
# A spec section may declare `line_roles` (thank-you-v1.json section 2: H2, Body, Body): the role of each
# copy line in order, which line_role and wireframe_spec._type_elements read instead of guessing from position.
DECLARED_ROLES = {"h1": "headline", "h2": "heading", "subhead": "short", "body": "body", "step": "step"}


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


def line_role(line, first, declared=None):
    """The role of one copy line. `declared` is the spec's own role for it (H1, H2, Subhead, Body or
    Step); without one the role is guessed from the line's position and length."""
    if declared:
        return DECLARED_ROLES[str(declared).lower()]
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
    desktop_px, mobile_px = {"headline": (56, 40), "heading": (44, 28), "short": (30, 24)}.get(role, (19, 16))
    per_line = lambda content, px: max(1, min(75, int(content / (px * 0.5))))
    lines = lambda content, px: -(-len(text) // per_line(content, px))
    return lines(1200, desktop_px), lines(342, mobile_px)


def section_fragments(stage, section, index, sections, spec, table, kind=None):
    """Ordered specification paragraphs for one section; each is added only while it fits."""
    sid = exe.canon_section_id(section["section_id"])
    n = len(sections)
    names = [s["section_name"] for s in sections]
    spec_section = next((x for x in spec["sections"] if exe.canon_section_id(x["id"]) == sid), {})
    row = table.get(sid, {})
    lines = [l for l in str(section.get("copy") or "").splitlines() if l.strip()]
    declared = section.get("line_roles")
    roles = [line_role(l, i == 0, (declared[i] if i < len(declared) else "Body") if declared else None)
             for i, l in enumerate(lines)]
    out = []
    near = [f"directly below {names[index - 2]}" if index > 1 else "at the top of the page, under the header",
            f"directly above {names[index]}" if index < n else "the last section before the footer"]
    out.append(f"SECTION SPECIFICATION: this slice is section {index} of {n}, {section['section_name']}, "
               f"{near[0]} and {near[1]}. Draw this section only.")
    purpose = [x.rstrip(".") for x in map(neutral, (row.get("purpose"), spec_section.get("job")))
               if x and not PRIVATE_TEXT.search(x)]
    if purpose:
        out.append("PURPOSE: " + "; ".join(purpose) + ".")
    if spec.get("layout_reference") and stage not in exe.wireframe_spec.WIREFRAME_STAGES:
        out.append("PAGE LAYOUT: " + spec["layout_reference"])  # the wireframe block carries it for wireframes
    # first, so the run's planned slots win the budget the new contract blocks left.
    # The canon names the section's OWN planned slots (id, ratio, art direction) rather than
    # pasting the skeleton table's prose cell: that cell carries private labels on sections 1
    # and 12 (the CTA BUTTON marker, the founder-letter parts), which the private-text screen
    # would drop whole, leaving the hero and the founder portrait unannounced.
    landing_form = spec.get("copy_version") in ("standard", "long-form") and not spec.get("form")
    if section.get("slots") and landing_form:  # the landing plan governs; other forms keep their own layout
        planned = []
        for slot in section["slots"]:
            if not isinstance(slot, dict):
                continue
            direction = str(slot.get("art_direction") or "").strip().rstrip(".")
            planned.append("%s (%s)%s" % (slot.get("slot_id") or "slot",
                                          slot.get("aspect_ratio") or "planned ratio",
                                          " " + direction if direction else ""))
        if planned:
            out.append("SLOT CANON: " + "; ".join(planned) +
                       ". Draw each slot once at that ratio; zero placeholders.")
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
    many = exe.cta_labels(section)
    forbidden = {exe.canon_section_id(x) for x in (spec.get("cta_map", {}).get("forbidden_in_sections") or [])}
    closing = page_kinds.closing_label(kind, section, sections, index, n)  # SPF030
    if len(many) > 1:
        if section.get("cta_layout") == "utility":
            note = str(section.get("cta_note") or "").strip().rstrip(".")
            if not note:  # the spec states the treatment; a guessed one is a defect
                raise BuildError(f"section {section.get('section_id')}: the utility actions carry "
                                 "no declared treatment (cta_note); rebuild the request from the "
                                 "spec, never a guessed treatment")
            place = note[0].lower() + note[1:]
        else:
            place = "one inside each package card in card order"
        out.append(f"BUTTON: this section carries exactly {len(many)} buttons, {place}, "
                   "labelled " + ", ".join(f'"{x}"' for x in many) +
                   "; no other button, link row or sticky bar.")
    elif cta:
        # a label of 8 words or more is named by pointing at the CTA LABEL line: quoting it again would
        # be an 8-word sequence repeated, which the prompt validator reads as padding
        label = "labelled exactly as the CTA LABEL line above" if len(cta.split()) >= 8 else f'labelled "{cta}"'
        out.append(f"BUTTON: this section carries exactly one button, {label}, with the microcopy "
                   "line under it when the copy block supplies one; no second button, link row or sticky bar.")
    elif closing:  # the last section carries no CTA of its own; the page kind's closing panel does
        out.append(f'BUTTON: this section carries no button of its own; its closing panel carries exactly one, '
                   f'labelled "{closing}"; no second button, link row or sticky bar.')
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
        # a declared heading is named, never quoted again: its words print once, in the verbatim block
        opening = "" if role == "heading" else f" opening \"{' '.join(line.split()[:4])}\""
        plan.append(f"{i} {role}{opening} ({len(line.split())} words)")
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
        # the verbatim copy is masked, as validate_prompt masks it: packages share inclusion lines word for word
        prompt = prompt.replace(exe.copy_contract(section), " ")
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
    # the skeleton table is the Standard and Long-Form guides' own; a registered form carries its own, a role spec its slot canon
    table = spec.get("skeleton") or (role_table(spec) if spec.get("form") else
                                     skeleton_table() if spec["copy_version"] in ("standard", "long-form") else {})
    for index, section in enumerate(request["sections"], start=1):
        parts = [str(section.get("layout") or "").strip()]
        parts = [p for p in parts if p]
        for text in section_fragments(stage, section, index, request["sections"], spec, table,
                                      request.get("page_kind")):
            if PRIVATE_TEXT.search(text):
                continue
            section["layout"] = "\n".join(parts + [text])
            try:
                fits_band = worst_size(request, stage, index, section) <= ceiling
            except exe.ExecutorError:  # a long fragment overshot the model maximum: skip it, try a shorter one
                continue
            if fits_band:
                parts.append(text)
        section["layout"] = "\n".join(parts)


class BuildError(Exception):
    pass


def check_slot_boxes(request):
    """A slot's `delivery_px` (the pixel box the wireframe's plate label prints: {desktop: [w, h], mobile: [w, h]})
    must be two positive integers per viewport at the slot's own ratio; a box that contradicts the ratio is the
    mislabelled plate the W3 trait exists to stop."""
    for section in request["sections"]:
        for slot in section.get("slots") or []:
            px = slot.get("delivery_px") if isinstance(slot, dict) else None
            if px is None:
                continue
            ratio = section_plan.vw.parse_ratio(slot.get("aspect_ratio"))
            for viewport in ("desktop", "mobile"):
                box = px.get(viewport) if isinstance(px, dict) else None
                ok = (isinstance(box, list) and len(box) == 2
                      and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in box))
                if not ok:
                    raise BuildError(f"section {section['section_id']} slot {slot.get('slot_id')!r}: delivery_px "
                                     f"{viewport} must be [width, height] in whole pixels, not {box!r}")
                if ratio is not None and abs(box[0] / box[1] - ratio) / ratio > section_plan.vw.RATIO_TOLERANCE:
                    raise BuildError(f"section {section['section_id']} slot {slot.get('slot_id')!r}: its {viewport} "
                                     f"box {box[0]} x {box[1]} is not the slot's ratio {slot.get('aspect_ratio')}")


def apply_inventory(request, run_dir) -> bool:
    """A page role's slots take their label from the run's closed image inventory
    (desktop-wireframe/image-inventory.json): the inventory id the plate prints (`inventory_id`), its treatment
    and, when it records one, its pixel box. A slot that disagrees with its inventory entry in ratio or treatment
    is refused by name; a slot the inventory does not hold is left alone (the plan writer refuses it). No
    inventory yet (a run's first pass) changes nothing. True when any slot was matched."""
    inventory = Path(run_dir) / section_plan.INVENTORY
    if not request.get("page_role") or not inventory.is_file():
        return False
    try:
        by_id, _entries = section_plan.inventory_for(run_dir)
        matched = False
        for section in request["sections"]:
            for slot in section.get("slots") or []:
                found = section_plan.match_slot(slot, by_id) if isinstance(slot, dict) else None
                if not found:
                    continue
                eid, entry = found
                section_plan.check_slot(section["section_id"], slot, eid, entry)
                slot["inventory_id"] = eid
                if entry.get("treatment"):
                    slot["treatment"] = entry["treatment"]
                if isinstance(entry.get("delivery_px"), dict):
                    slot["delivery_px"] = entry["delivery_px"]
                matched = True
    except section_plan.PlanError as exc:
        raise BuildError(str(exc))
    return matched


def apply_font_map(request, stage, run_dir) -> bool:
    """Each wireframe section's `type_specs` are the closed font plan's sizes (font-action-plan/font-map.json),
    as desktop and tablet (desktop-wireframe) or tablet and mobile (mobile-tablet), so the sheet prints the run's
    sizes and not the house scale's ranges. An element the font plan does not size (a subhead, the CTA microcopy)
    keeps its house-scale range. No font map in the run changes nothing. True when type specs were set."""
    try:
        font_map = font_sizes.load(run_dir)
    except font_sizes.FontMapError as exc:
        raise BuildError(str(exc))
    if font_map is None:
        return False
    scale = wireframe_spec.spec()["type_scale_default"][stage]
    house = {k.lower(): (k, v) for k, v in scale.items()}
    sections, kind = request["sections"], request.get("page_kind")
    for index, section in enumerate(sections, start=1):
        closing = None
        if kind:
            try:
                label = page_kinds.closing_label(kind, section, sections, index, len(sections))
            except page_kinds.KindError as exc:
                raise BuildError(str(exc))
            closing = label if label and not wireframe_spec._cta(section) else None
        specs = {}
        for element in wireframe_spec._type_elements(section, closing):
            value = font_sizes.caption(font_map, element, stage) or (house.get(element.lower()) or (None, None))[1]
            if value:
                specs[element] = value
        if specs:
            section["type_specs"] = specs
    return True


# A manuscript link `[Choose your seat](https://...)` is the page's link, not its printed words: the
# copy block carries the label only, or the render prints the bracket, the parentheses and the URL.
MD_LINK = re.compile(r"\[([^\]\n]+)\]\([^)\s]+\)")

def section_copy(units):
    """Public copy lines of one section, and its single CTA button label."""
    lines, buttons = [], []
    for u in units:
        text = MD_LINK.sub(r"\1", u.text)
        if u.kind == "cta_button":
            buttons.append(text)
        elif u.kind == "step":
            lines.append(f"{u.step_no}. {text}")
        else:
            lines.append(text)
    return "\n".join(lines), buttons


def spec_label(spec: dict) -> str:
    return f"{spec['page_role']} page" if spec.get("page_role") else f"{spec['copy_version']} copy"


def role_table(spec: dict) -> dict:
    """The role spec's per-section slot canon, in the shape skeleton_table() has for landing."""
    return {s["id"]: {"purpose": None, "slots": s.get("slot_canon", "")} for s in spec["sections"]}


def role_section_fields(spec: dict, sid: str, slots: dict, buttons: list) -> dict:
    """What a role spec adds to a request section: slots (the caller's, else the spec's), the
    composition role, ground, behaviour note and the desktop / mobile layout. Also the
    spec's one-button rule, refused by name."""
    cta_map = spec.get("cta_map") or {}
    if buttons and sid in cta_map.get("forbidden_in_sections", []):
        raise BuildError(f"section {sid}: a button is not allowed here on the {spec_label(spec)} "
                         f"({cta_map.get('rule', '')})")
    if not buttons and sid in cta_map.get("required_in_sections", []):
        raise BuildError(f"section {sid}: the {spec_label(spec)} needs its button here "
                         f"({cta_map.get('rule', '')})")
    sec = role_spec.section(spec, sid)
    out = {"section_name": sec["name"], "composition_role": sec["composition_role"],
           "ground": sec["ground"], "behavior_notes": sec["behavior_notes"],
           "layout": f"DESKTOP LAYOUT: {sec['desktop']}\nMOBILE LAYOUT: {sec['mobile']}",
           "slots": copy.deepcopy(slots[sid] if sid in slots else sec["slots"])}
    return out


def spec_slots(entry: dict, style_id) -> list:
    """A page-type section's default image slots, shaped for the client's design style
    (a slot's `shape_by_style`, `style_ratio` and `treatment_by_style` pick circle, 1:1 and the
    circle-crop treatment for style B)."""
    by_style = ("shape_by_style", "style_ratio", "treatment_by_style")
    out = []
    for slot in entry.get("default_slots") or []:
        shaped = {k: v for k, v in slot.items() if k not in by_style}
        shape = (slot.get("shape_by_style") or {}).get(style_id)
        if shape:
            shaped["shape"] = shape
            shaped["aspect_ratio"] = (slot.get("style_ratio") or {}).get(style_id, shaped.get("aspect_ratio"))
        if (slot.get("treatment_by_style") or {}).get(style_id):
            shaped["treatment"] = slot["treatment_by_style"][style_id]
        out.append(shaped)
    return out


def closed_headings(run_dir, spec: dict):
    """{section id: closed heading} from the run's closed export, copy/public-copy.md: its `## ` lines in
    order, one per canonical section of the spec's sequence. None when the run has no export (the caller
    names its fallback). A heading count that differs from the sequence is a named refusal: a guessed
    pairing would print one section's heading over another's copy."""
    path = Path(run_dir) / "copy" / "public-copy.md"
    if not path.is_file():
        return None
    found = [l[3:].strip() for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("## ")]
    sequence = list(spec["sequence"])
    if len(found) != len(sequence) or not all(found):
        raise BuildError(f"copy/public-copy.md has {len(found)} section heading(s) ({found}); the "
                         f"{spec_label(spec)} has {len(sequence)} canonical sections {sequence}, so a closed "
                         "heading cannot be paired with its section")
    return dict(zip(sequence, found))


def sections_from_manuscript(text: str, spec: dict, slots: dict, style_id=None, order_bump=None,
                             headings=None) -> list:
    names = spec.get("role_names") or {}
    units, order, _notes = parse_manuscript(text)
    allowed = page_role.allowed_sequences(spec, {"order_bump": order_bump})  # the same resolver the executor's check reads
    if order not in allowed:
        want = allowed[0]
        raise BuildError(
            f"section count: the manuscript has {len(order)} sections {order} but the "
            f"{spec_label(spec)} has {len(want)} canonical sections {want}; "
            f"missing {[i for i in want if i not in order]}, unexpected "
            f"{[i for i in order if i not in want]}")
    sequence = order  # the matched sequence, so an optional 5A/5B/5C expansion builds one section per child
    role_page = bool(spec.get("page_role"))
    entries = {e["id"]: e for e in spec["sections"]}
    kids = page_role.child_names(spec)
    # A page type whose spec forbids offer buttons carries utility actions only (support,
    # access, manage purchase): its `rules.offer_buttons` says so.
    rules = spec.get("rules") if isinstance(spec.get("rules"), dict) else {}
    utility_page = rules.get("offer_buttons") == "forbidden"
    out = []
    for sid in sequence:
        copy, buttons = section_copy([u for u in units if u.section == sid])
        spec_section = entries.get(sid, {})
        # The spec's own multiplicity, from its `cta.standalone` declaration: "forbidden" allows
        # no button at all, "per_card" one button per package card (the spec's `min` is the
        # floor), and "optional" on a utility page carries its utility actions side by side.
        # Everything else is landing's one button.
        cta_rule = spec_section.get("cta") if isinstance(spec_section.get("cta"), dict) else {}
        standalone = cta_rule.get("standalone")
        per_card = standalone == "per_card"
        utility = standalone == "optional" and utility_page
        if buttons and standalone == "forbidden":
            raise BuildError(f"section {sid}: {len(buttons)} CTA buttons {buttons}; the "
                             f"{spec_label(spec)} forbids a button in this section")
        if per_card and cta_rule.get("min") and len(buttons) < int(cta_rule["min"]):
            raise BuildError(f"section {sid}: the {spec_label(spec)} needs at least {cta_rule['min']} "
                             f"package buttons, one per card; the manuscript carries {len(buttons)}")
        if len(buttons) > 1 and not (per_card or utility):
            raise BuildError(f"section {sid}: {len(buttons)} CTA buttons {buttons}; "
                             "one button per section")
        declared_roles = spec_section.get("line_roles")
        if declared_roles is not None and (not isinstance(declared_roles, list) or not declared_roles
                                           or any(str(r).lower() not in DECLARED_ROLES for r in declared_roles)):
            raise BuildError(f"section {sid}: line_roles {declared_roles!r} must be a non-empty list of "
                             "H1, H2, Subhead, Body or Step")
        heading = None
        if spec_section.get("copy_heading"):
            # The section's closed heading is the first line of its copy: the manuscript has none (a
            # heading is not counted copy), the closed export does. No export: the spec's own section name.
            heading = (headings or {}).get(sid) or spec_section.get("name") or names.get(sid)
            copy = f"{heading}\n{copy}" if copy else heading
        entry = {"section_id": sid,
                 "section_name": (names.get(sid) or kids.get(sid)
                                  or (spec_section.get("name") if role_page else None)
                                  or ROLE_NAMES.get(sid)),
                 "copy": copy,
                 "cta": None if (per_card or len(buttons) > 1) else (buttons[0] if buttons else None),
                 # Every copy spec that carries image slots declares them as `default_slots`
                 # on its section (standard/long-form v6: one row per section of the
                 # section-image-prompt.md skeleton table; page roles: thank-you). The
                 # fallback is not gated on `page_role`: a landing spec that leaves its
                 # slots empty is exactly how a page plans no image and ships a mockup
                 # with two pictures in it.
                 "slots": slots.get(sid) or spec_slots(spec_section, style_id)}
        if per_card or len(buttons) > 1:  # one per package card, or the page type's own utility actions
            entry["cta_labels"] = buttons
            if utility:
                # Keep the treatment: the spec's own note says which action is filled and which
                # are outlined (section 5) or that each access card carries its own (section 3).
                # Never the landing/product-selection package-card rule, and never a guess.
                note = str(cta_rule.get("note") or "").strip()
                if not note:
                    raise BuildError(f"section {sid}: the {spec_label(spec)} carries its utility "
                                     "actions side by side but its cta block declares no note; the "
                                     "treatment must come from the spec, never a guess")
                entry["cta_layout"] = "utility"
                entry["cta_note"] = note
        # a non-landing form's spec pins each section's composition role, ground and behaviour note
        for key, field in (("composition_role", "composition_role"), ("ground", "ground")):
            if spec_section.get(field):
                entry[key] = spec_section[field]
        if spec_section.get("behavior_notes"):
            entry["behavior_notes"] = spec_section["behavior_notes"]
        if declared_roles:
            entry["line_roles"] = list(declared_roles)
        if heading:
            entry["copy_heading"] = heading
            entry["copy_heading_source"] = ("copy/public-copy.md" if (headings or {}).get(sid)
                                            else "the spec section name (the run has no copy/public-copy.md)")
        if spec.get("form"):  # a role spec (references/copy-specs/roles/): name, slots, layout, one-button rule
            entry.update(role_section_fields(spec, sid, slots, buttons))
        # The founder letter ends with the founder's signature (copy spec, Section 12
        # Part 6): a name, not a sentence. It is a verbatim label of its own so the
        # executor's truncated-copy guard keeps reading prose only.
        rows = copy.splitlines()
        if (sid == "12" or spec_section.get("signature_label")) and len(rows) > 1 and rows[-1][-1] not in exe.TERMINAL and len(rows[-1].split()) <= 8:
            entry["copy"], entry["labels"] = "\n".join(rows[:-1]), [rows[-1]]
        out.append(entry)
    return out


# One image slot per upsell section, IMG-001 to IMG-008 (the page's slot ids are unique), at
# these ratios. The picture follows the section's own heading, so the plan never invents an
# offer claim. A run's own plan (--slots) replaces it.
UPSELL_RATIOS = {"1": "16:9", "2": "4:3", "3": "3:2", "4": "4:3", "5": "3:2", "6": "1:1",
                 "7": "4:3", "8": "3:2"}


def upsell_layouts(plan):
    """{section id: layout entry} for the bundle's upsell instance from page-structures.json
    `layouts`, or None while that file declares no layouts at all."""
    layouts = json.loads(Path(exe.STRUCTURES_FILE).read_text(encoding="utf-8")).get("layouts")
    if layouts is None:
        return None
    instance = (plan or {}).get("instance")
    entry = layouts.get(instance) if isinstance(layouts.get(instance), dict) else None
    if not entry:
        raise BuildError(f"the bundle's page_plan.instance {instance!r} has no layout in "
                         f"page-structures.json layouts ({', '.join(k for k in layouts if k != 'note')})")
    return {x["id"]: x for x in entry["sections"]}


def sections_from_copy_json(copy_doc: dict, bundle: dict, spec: dict, slots: dict) -> list:
    """Request sections from Skill 80's validated upsell copy and its result bundle.

    Copy lines per section: heading, body, bullets, numbered reasons, then (section 1) the
    order-confirmed lines and, last, the exact amount-and-terms line the CTA carries. Each
    section keeps its own CTA, the decline link label and those lines as fields the
    wireframe stage prints verbatim (wireframe_spec.page_type_lines)."""
    plan = bundle.get("page_plan") if isinstance(bundle, dict) else None
    disclosure = ((plan or {}).get("disclosure") or {}).get("text")
    ack = [b["text"] for b in (plan or {}).get("acknowledgement_blocks") or [] if b.get("text")]
    if not disclosure or not ack:
        raise BuildError("the bundle's page_plan needs disclosure.text and acknowledgement_blocks: "
                         "the upsell page prints the exact amount and terms under every CTA and "
                         "acknowledges the original purchase; neither is invented here")
    docs = copy_doc.get("sections") or []
    order = [exe.canon_section_id(d.get("number")) for d in docs]
    sequence = list(spec["sequence"])
    if order != sequence:
        raise BuildError(
            f"section count: the copy has {len(order)} sections {order} but the "
            f"{spec['copy_version']} copy has {len(sequence)} canonical sections {sequence}; "
            f"missing {[i for i in sequence if i not in order]}, unexpected "
            f"{[i for i in order if i not in sequence]}")
    names = {x["id"]: x["framework_name"] for x in spec["sections"]}
    layouts = upsell_layouts(plan)
    fell_back = []
    out = []
    for sid, doc in zip(sequence, docs):
        cta = (doc.get("cta") or {}).get("text")
        if not cta:
            raise BuildError(f"section {sid}: the upsell has a CTA in every section and this has none")
        lines = [doc["heading"], doc["body"]] + list(doc.get("bullets") or [])
        lines += [f"{n}. {r}" for n, r in enumerate(doc.get("reasons") or [], 1)]
        if sid == "1":
            lines += ack
        lines.append(disclosure)
        if layouts is not None:  # the declared band layout: never a picture derived from the heading
            band = layouts[sid]
            default = [{**band["slot"],
                        "art_direction": f"{band['geometry']} Image plate only; no plan was passed "
                                         "(--slots from 80-signature-upsell upsell_image_plan.py gives "
                                         "the offer-specific plan)"}]
            if sid not in slots:
                fell_back.append(sid)
        else:  # ponytail: page-structures.json carries no `layouts` yet; drop this branch once it does
            default = [{"slot_id": f"IMG-{int(sid):03d}", "aspect_ratio": UPSELL_RATIOS[sid],
                        "art_direction": f"Editorial photograph that illustrates: {doc['heading']}"}]
        entry = {"section_id": sid, "section_name": names[sid], "copy": "\n".join(lines),
                 "cta": cta, "terms": disclosure, "decline": spec["decline_label"],
                 "slots": slots.get(sid, default),
                 "behavior_notes": "One-click accept CTA; decline never charges"}
        if layouts is not None:
            entry["layout_tag"] = layouts[sid]["layout_tag"]
        if sid == "1":
            entry["ack"] = ack
        out.append(entry)
    if fell_back:
        print(f"NOTE: no image plan for upsell section(s) {', '.join(fell_back)}; each carries its "
              "declared layout's image plate", file=sys.stderr)
    return out


def sections_from_page(doc: dict, structure: dict, slots: dict, notes: dict) -> list:
    """Request sections from a non-landing page's own copy document, one per
    section of the role's structure, in order. A role label used as a heading
    ("The Big Bold Claim") is a framework name, never public copy: it is
    dropped and the body prints. A list item without closing punctuation gets
    a full stop so the executor's truncated-copy guard reads it as finished;
    both are recorded in `notes`."""
    page = doc.get("page") if isinstance(doc.get("page"), dict) else doc
    rows = page.get("sections")
    wanted = [s["page_role"] for s in structure["sections"]]
    got = [r.get("role") if isinstance(r, dict) else None for r in rows or []]
    if got != wanted:
        raise BuildError(
            f"section count: the {structure['label']} copy has {len(got)} sections {got} but "
            f"the {structure['role']} structure has {len(wanted)} sections {wanted}")
    decline = str(((page.get("decline_action") or {}).get("label")) or "").strip()
    if not decline:
        raise BuildError("the page copy carries no decline_action.label; the decline button is "
                         "part of every band of this page type")
    out = []
    for spec_sec, row in zip(structure["sections"], rows):
        sid = spec_sec["id"]
        lines = []
        heading = str(row.get("heading") or "").strip()
        if heading and not PRIVATE_TEXT.search(heading):
            lines.append(heading)
        elif heading:
            notes["dropped_role_label_headings"].append(sid)
        lines += [p.strip() for p in re.split(r"\n\s*\n", str(row.get("body") or "")) if p.strip()]
        for n, item in enumerate(row.get("missed_out_items") or [], start=1):
            item = str(item).strip()
            if item[-1:] not in exe.TERMINAL:
                item += "."
                notes["terminal_periods_added"].append(f"{sid}.{n}")
            lines.append(f"{n}. {item}")
        label = ((row.get("cta") or {}).get("label")) or ""
        if not str(label).strip():
            raise BuildError(f"section {sid}: no CTA label; every band of this page type has a button")
        out.append({"section_id": sid, "section_name": spec_sec["name"], "copy": "\n".join(lines),
                    "cta": str(label).strip(), "labels": [decline], "layout": spec_sec.get("layout", ""),
                    "slots": slots.get(sid, spec_sec.get("slots", []))})
    return out


def template_for(stage: str, blocks: dict) -> str:
    parts = [LEADS[stage]]
    for key, heading in BLOCKS:
        if blocks.get(key):
            # EVERY block, not only rules_json: a literal brace anywhere in the prose
            # (the measured design system embeds the font map as JSON) raised
            # "unknown placeholder" from str.format, sizes_for()'s caller read the trial
            # as "does not fit", and the binary-search trim silently kept only the
            # prefix before the first brace. The documented remedy ("supply
            # --design-prose with the run's measured design system") therefore failed
            # with no error and no growth. Escaping here is what makes the prose usable.
            body = str(blocks[key]).replace("{", "{{").replace("}", "}}")
            parts += [heading, body]
    if blocks.get("brand_style"):  # the design library card, verbatim; braces survive str.format
        parts += [BRAND_STYLE_HEAD, blocks["brand_style"].replace("{", "{{").replace("}", "}}")]
    parts.append(SECTION_BODY if stage in MOCKUP_PROMPT_STAGES else SECTION_TAIL)
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


def folded_levels(run_dir):
    """N when the run's launch record (<run_dir>/launch.json, staged by write_intake --launch-context)
    folds N levels into the sales page (journey_mode folded_levels: its N main offers), else None."""
    try:
        launch = json.loads((Path(run_dir) / "launch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(launch, dict) or launch.get("journey_mode") != "folded_levels":
        return None
    # a launch record names an offer's place in the journey as "slot" (83 to_launch_record); "role"
    # is read only as a legacy alias
    mains = [o for o in launch.get("offers") or []
             if isinstance(o, dict) and (o.get("slot") or o.get("role")) == "main"]
    return len(mains) if len(mains) >= 2 else None


LAYOUT_OVERRIDE_KEYS = ("layout", "negatives", "aspect_ratio", "mobile_layout", "mobile_negatives")
# SWB-560: `mobile_layout` / `mobile_negatives` are design text only the phone slice's prompt receives
# (kept in the section's `layout_mobile`, never merged into `layout`), so editing a section's mobile entry
# re-keys that section's mobile slice and leaves its desktop slice settled. Same stages as aspect_ratio.
# SWB-290: stages that draw a mobile slice (the only viewport an aspect_ratio override reaches)
ASPECT_OVERRIDE_STAGES = ("mobile-tablet", "visual-mockup", "final-mockups")


def _slot_ratio(section):
    """The fixed ratio of the section's first non-circle slot, or None when it has none ("auto" is none)."""
    flat = [x for x in section.get("slots") or [] if exe.design_style.slot_shape(x) != "circle"]
    ratio = (flat or [{}])[0].get("aspect_ratio")
    return ratio if ratio and ratio != "auto" else None


def _check_aspect_override(stage_key, sid, value, section):
    """SWB-290: the design-only mobile frame ratio of a section that has no image slot to set it."""
    where = f"layout overrides: {stage_key!r} section {sid!r} `aspect_ratio`"
    if stage_key not in ASPECT_OVERRIDE_STAGES:
        raise BuildError(f"{where} applies to a stage that draws a mobile slice "
                         f"({', '.join(ASPECT_OVERRIDE_STAGES)}), not {stage_key!r}")
    if not isinstance(value, str) or value not in exe.RATIO_ENUM:
        raise BuildError(f"{where} must be one of {', '.join(exe.RATIO_ENUM)}, not {value!r}")
    a, b = (int(x) for x in value.split(":"))
    if a > b:
        raise BuildError(f"{where} {value!r} is landscape; the mobile frame is portrait or square")
    slot = _slot_ratio(section)
    if slot is not None and slot != value:
        raise BuildError(f"{where} {value!r} would override the section's image slot ratio {slot!r}; "
                         "a section that has a slot keeps the slot's ratio (override only a section with no slot)")


def load_layout_overrides(path, stage, sections):
    """SWB-200: the sanctioned per-run design-text input. Returns None when no file is given, else
    {"source", "sha256", "stage", "applied": [...]} and appends each entry to that stage's section
    `layout` field. Design text only: any key but `layout` / `negatives` refuses, a stage or a
    section id the page does not have refuses, and copy, ctas, model, references, slots and section
    order are never reachable from here."""
    if path is None:
        return None
    path = Path(path)
    try:
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError(f"layout overrides {path}: cannot be read as JSON: {exc}")
    if not isinstance(doc, dict):
        raise BuildError(f"layout overrides {path}: the file must be an object keyed by stage")
    ids = {str(s["section_id"]): s for s in sections}
    for stage_key, per_section in doc.items():
        if stage_key not in exe.STAGES:
            raise BuildError(f"layout overrides: unknown stage {stage_key!r} "
                             f"(stages: {', '.join(exe.STAGES)})")
        if not isinstance(per_section, dict):
            raise BuildError(f"layout overrides: stage {stage_key!r} must be an object keyed by section id")
        for sid, entry in per_section.items():
            if str(sid) not in ids:
                raise BuildError(f"layout overrides: stage {stage_key!r} names unknown section {sid!r} "
                                 f"(sections: {', '.join(ids)})")
            if not isinstance(entry, dict):
                raise BuildError(f"layout overrides: {stage_key!r} section {sid!r} must be an object")
            extra = sorted(set(entry) - set(LAYOUT_OVERRIDE_KEYS))
            if extra:
                raise BuildError(f"layout overrides: {stage_key!r} section {sid!r} carries "
                                 f"{', '.join(extra)}; only {' and '.join(LAYOUT_OVERRIDE_KEYS)} (design "
                                 "text) can be overridden, never copy, ctas, model, references, slots "
                                 "or section order")
            if "aspect_ratio" in entry:
                _check_aspect_override(stage_key, sid, entry["aspect_ratio"], ids[str(sid)])
            if "mobile_layout" in entry or "mobile_negatives" in entry:
                where = f"layout overrides: {stage_key!r} section {sid!r}"
                if stage_key not in ASPECT_OVERRIDE_STAGES:
                    raise BuildError(f"{where} `mobile_layout` applies to a stage that draws a mobile slice "
                                     f"({', '.join(ASPECT_OVERRIDE_STAGES)}), not {stage_key!r}")
                if not isinstance(entry.get("mobile_layout"), str) or not entry["mobile_layout"].strip():
                    raise BuildError(f"{where} needs a non-empty `mobile_layout` string "
                                     "(`mobile_negatives` goes with it)")
                if "mobile_negatives" in entry and not isinstance(entry["mobile_negatives"], str):
                    raise BuildError(f"{where} `mobile_negatives` must be a string")
            only_mobile = "mobile_layout" in entry and "layout" not in entry and "negatives" not in entry
            if "aspect_ratio" in entry and "layout" not in entry and "negatives" not in entry:
                pass  # a frame-ratio-only entry appends no text (SWB-300: but never carries negatives with it)
            elif only_mobile:
                pass  # a mobile-only entry appends no text to the shared layout (SWB-560)
            elif not isinstance(entry.get("layout"), str) or not entry["layout"].strip():
                raise BuildError(f"layout overrides: {stage_key!r} section {sid!r} needs a non-empty "
                                 "`layout` string")
            if "negatives" in entry and not isinstance(entry["negatives"], str):
                raise BuildError(f"layout overrides: {stage_key!r} section {sid!r} `negatives` must be a string")
    applied = []
    for sid, entry in (doc.get(stage) or {}).items():
        section = ids[str(sid)]
        text = ""
        if "layout" in entry:
            text = entry["layout"].strip()
            if entry.get("negatives", "").strip():
                text += "\nNEGATIVES: " + entry["negatives"].strip()
            section["layout"] = "\n".join(([section["layout"]] if section.get("layout") else []) + [text])
        row = {"section_id": str(section["section_id"]), "appended_text": text}
        if entry.get("mobile_layout"):  # SWB-560: the phone slice's own design text; the desktop prompt never sees it
            mobile = entry["mobile_layout"].strip()
            if entry.get("mobile_negatives", "").strip():
                mobile += "\nNEGATIVES: " + entry["mobile_negatives"].strip()
            section["layout_mobile"] = mobile
            row["mobile_text"] = mobile
            row["viewport"] = "mobile"
        if "aspect_ratio" in entry:  # design-only; stage_executor.target_ratio reads it for the mobile slice
            section["layout_aspect_ratio"] = {"stage": stage, "viewport": "mobile", "ratio": entry["aspect_ratio"]}
            row["aspect_ratio"] = entry["aspect_ratio"]
            row["viewport"] = "mobile"
        applied.append(row)
    return {"source": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "stage": stage,
            "applied": applied}


def build(stage, version, manuscript_text, slots, prose, references, model, style, run_dir=Path("."),
          page_role="landing", sections=None, structure=None, page_doc=None, page_kind=None,
          order_bump=None, style_card=None, layout_overrides=None):
    notes = {"dropped_role_label_headings": [], "terminal_periods_added": []}
    if structure:  # a role with its own entry in references/page-structures.json (downsell_1)
        version, spec = structure["copy_version"], structure
        sections = sections_from_page(page_doc, structure, slots, notes)
    else:
        role_form = copy_forms.form_for_role(page_role)  # the one registry: it reads plural page_roles too
        spec = role_spec.load(page_role)
        if spec:
            # the executor's own rule for a role spec (check_section_count): that role is built
            # from a landing form's style reference, never from a page type's own form
            if version and version not in role_spec.FORMS:
                raise BuildError(
                    f"--copy-version {version!r} does not fit page role {page_role!r}: that role "
                    f"is drawn from the {', '.join(role_spec.FORMS)} form (a page type is never "
                    "forced into another's sections)")
            version = version or spec["form"]
        else:
            if role_form and version and version != role_form:
                raise BuildError(
                    f"--copy-version {version!r} does not fit page role {page_role!r}: that role "
                    f"is drawn from the {role_form!r} form (a page type is never forced into "
                    "another's sections)")
            version = version or role_form
            if not version:
                raise BuildError("--copy-version is required for a landing page (standard, long-form, product-selection or upsell)")
            if version not in copy_forms.SPEC_FILES:
                raise BuildError(f"--copy-version {version!r} is not one of {', '.join(copy_forms.FORMS)}")
            spec = copy_forms.load_spec(version)
        if sections is None:
            headings = (closed_headings(run_dir, spec)
                        if any(s.get("copy_heading") for s in spec.get("sections") or []) else None)
            sections = sections_from_manuscript(manuscript_text, spec, slots, exe.style_id_for(Path(run_dir), {}),
                                                order_bump, headings)
        elif stage not in wireframe_spec.WIREFRAME_STAGES:
            # A wireframe prompt carries the page type's lines itself (wireframe_spec.prompt_block);
            # the mockup stages take them through the section layout.
            for section in sections:
                section["layout"] = "\n".join(wireframe_spec.page_type_lines(
                    version, section, wireframe_spec.section_tag(section, 1)))
    overrides = load_layout_overrides(layout_overrides, stage, sections)
    kind = None
    if page_role == "landing" and not spec.get("page_role"):  # SPF030: only a landing-role page has a kind
        try:  # the page kind (flag, else the run's intake) must allow this copy form
            kind = page_kinds.normalize(page_kind) if page_kind else page_kinds.declared(run_dir, {})
            if kind:
                page_kinds.check(kind, version)
        except page_kinds.KindError as exc:
            raise BuildError(f"page kind: {exc}")
    # The page role the request IS. A spec names one role in `page_role`, or several in
    # `page_roles` (the upsell form serves upsell_1 and upsell_2): the runner's verified role
    # is stamped, and a role the form does not serve is refused rather than silently landing.
    built_role = spec.get("page_role")
    if not built_role and spec.get("page_roles"):
        served = list(spec["page_roles"])
        if page_role not in served:
            raise BuildError(
                f"page role {page_role!r} is not one of {served} for the {spec['copy_version']} "
                "form; pass --page-role with the role this page runs as (the runner verifies it "
                "against the bundle)")
        built_role = page_role
    elif built_role and page_role not in (built_role, "landing"):
        # "landing" is the documented default (the form's own role is stamped); any other role
        # must be the form's, never silently overridden by the spec
        raise BuildError(
            f"page role {page_role!r} does not serve the {spec['copy_version']} form: that form "
            f"is the {built_role} page's own (a page type is never forced into another's "
            "sections)")
    prose = json.loads(neutral(json.dumps(prose)))  # a reference's "Pain 01" band label is a framework name too
    request = {"model": model, "style": style, "copy_version": version,
               "references": references, "sections": sections,
               "stage_prompts": {stage: template_for(stage, {})}}
    if built_role:
        request["page_role"] = built_role
    if overrides:
        request["layout_overrides"] = overrides
    if spec.get("form"):
        request["_role_spec"] = spec  # the wireframe block reads it; never written out
    if order_bump is not None:  # the funnel's bump decision; the executor reads the same key
        if spec.get("page_role") not in BUMP_SECTION:
            raise BuildError(f"the order bump decision applies to a checkout page, not the {spec_label(spec)}")
        request["order_bump"] = bool(order_bump)
    if structure:
        page = page_doc.get("page") if isinstance(page_doc.get("page"), dict) else page_doc
        request["page_role"] = structure["role"]
        request["decline_action"] = {"label": page["decline_action"]["label"].strip()}
    if kind:
        request["page_kind"] = kind
        levels = folded_levels(run_dir) if kind == "sales" else None
        if levels:  # the sales page closes on an N-card levels panel (wireframe_spec / page_kinds)
            request["folded_levels"] = levels
    slot_labels = font_sizes_applied = False
    if stage in wireframe_spec.WIREFRAME_STAGES:
        check_slot_boxes(request)
        slot_labels = apply_inventory(request, run_dir)
        font_sizes_applied = apply_font_map(request, stage, run_dir)
    run_blocks(request, run_dir)
    budget = exe.prompt_budget(model)
    chosen = {}
    if style_card:  # the card is part of the contract: set first, so prose gives way to it, never the reverse
        unfilled = sorted(set(re.findall(r"\{[A-Za-z_]\w*\}", style_card["long_tier"])))
        if unfilled:  # the executor refuses a leftover token; say why, by card, before composing anything
            raise BuildError(f"style card {style_card['id']}: its LONG tier still carries the unfilled "
                             f"variable(s) {', '.join(unfilled)}; a template variable is never sent to a model, "
                             "so fill the card's variables in the design library (Skill 45 Workflow B) first")
        chosen["brand_style"] = style_card["long_tier"]
        request["stage_prompts"][stage] = template_for(stage, chosen)

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
        "stage": stage, "copy_version": version, "page_role": built_role or "landing",
        "page_kind": kind, "section_count": len(sections),
        "canonical_ids": [s["section_id"] for s in sections], "provider_calls": 0,
        **({"page_role": structure["role"], **notes} if structure else {}),
        "dropped_blocks": [k for k, _h in BLOCKS if prose.get(k) and k not in chosen],
        "trimmed_blocks": [k for k in chosen if k != "brand_style" and chosen[k] != prose[k]],
        **({"style_card": {"id": style_card["id"], "sha256": style_card["sha256"]}} if style_card else {}),
        "char_budget": {"target": budget and budget["target_chars"],
                        "max": budget and budget["max_chars"],
                        "min_seen": min(sizes.values()), "max_seen": max(sizes.values()),
                        "per_section": sizes},
    }
    if font_sizes_applied:
        request["metadata"]["type_specs_source"] = str(font_sizes.FONT_MAP)
    if slot_labels:
        request["metadata"]["slot_labels_source"] = str(section_plan.INVENTORY)
    padding_check(request, stage)
    # Fail closed on our own output, against the run this manuscript belongs to.
    request["metadata"]["checked_against"] = exe.check_section_count(run_dir, request, paid=True)[2]
    # The run's palette is re-resolved by the executor; it is never written into the request.
    for key in ("_brand_block", "_hypersat", "_role_spec"):
        request.pop(key, None)
    return request


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--copy-version", choices=list(copy_forms.FORMS),
                   help="the copy form (standard, long-form, product-selection, upsell); optional for a page "
                        "role that has its own spec")
    p.add_argument("--page-role", default="landing",
                   help="page role (default landing); a role with references/copy-specs/roles/<role>.json "
                        "is built to that role's section sequence, a role with an entry in "
                        "references/page-structures.json (downsell_1) to that entry's sequence")
    p.add_argument("--manuscript", type=Path)
    p.add_argument("--copy-json", type=Path, help="upsell only: Skill 80's validated eight-section copy JSON")
    p.add_argument("--bundle", type=Path, help="upsell only: Skill 80's result bundle JSON")
    p.add_argument("--page-copy", type=Path,
                   help="a role with a references/page-structures.json entry: that role's own page copy document (JSON)")
    p.add_argument("--stage", choices=list(exe.STAGES), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--page-kind", choices=page_kinds.kind_ids(), default=None,
                   help="sales or opt_in (default: the run's intake.json page_kind); "
                        "references/page-kinds.json")
    p.add_argument("--no-bump", action="store_true",
                   help="checkout only: the funnel has no order bump, so the page has no section 3 "
                        "(without the flag the checkout keeps all five sections)")
    p.add_argument("--slots", type=Path)
    p.add_argument("--design-prose", type=Path)
    p.add_argument("--references", default="")
    p.add_argument("--model", default="gpt-image-2-6/sunburst-image-to-image")
    p.add_argument("--style", default="")
    p.add_argument("--style-card-id", default=None,
                   help="a registered Skill 45 style card; default: style_card_id in the run's intake.json. "
                        "Its LONG tier is embedded verbatim in every section prompt")
    p.add_argument("--layout-overrides", type=Path, default=None, metavar="PATH",
                   help="design text only: {stage: {section id: {layout, negatives}}} appended to that stage's "
                        "section layout (never replacing it); sha256 and applied text are recorded in the "
                        "request's `layout_overrides` block. Absent: nothing changes")
    p.add_argument("--run-dir", type=Path,
                   help="the run whose copy source and copy/copy-manifest.json the request is "
                        "checked against (default: the manuscript's run when it sits in "
                        "<run_dir>/copy/, else the folder of --out)")
    a = p.parse_args(argv)
    upsell = a.copy_version == "upsell"
    structure = exe.page_structure(a.page_role)
    if a.page_copy and not structure:
        print(f"REFUSED: page role {a.page_role!r} has no entry in references/page-structures.json")
        return 1
    if structure and not a.page_copy:
        p.error(f"{a.page_role} takes --page-copy (its own page copy document)")
    if not structure and ((upsell and not (a.copy_json and a.bundle)) or (not upsell and not a.manuscript)):
        p.error("upsell takes --copy-json and --bundle; every other form and page role takes --manuscript")
    source = a.page_copy if structure else a.copy_json if upsell else a.manuscript
    run_dir = a.run_dir or (source.resolve().parent.parent
                            if source.resolve().parent.name == "copy"
                            else a.out.resolve().parent)
    try:
        # Skill 45, read-only: every build reads the rules (a missing file refuses by name, AF-DI-ABSENT)
        # and the requested card; the receipt is written only after the request is built.
        card_id = a.style_card_id or di.run_style_card_id(run_dir)
        style_card = di.resolve_style_card(card_id) if card_id else None
        di.build_receipt(card_id)
        load = lambda f: json.loads(f.read_text(encoding="utf-8")) if f else {}
        sections = page_doc = None
        if structure:
            page_doc = load(a.page_copy)
        elif upsell:
            spec = json.loads((exe.SPEC_DIR / "upsell-v6.json").read_text(encoding="utf-8"))
            sections = sections_from_copy_json(load(a.copy_json), load(a.bundle), spec, load(a.slots))
        request = build(a.stage, a.copy_version, "" if (structure or upsell) else a.manuscript.read_text(encoding="utf-8"),
                        load(a.slots), load(a.design_prose),
                        [r for r in a.references.split(",") if r], a.model, a.style, run_dir,
                        a.page_role, sections=sections, structure=structure, page_doc=page_doc,
                        page_kind=a.page_kind, order_bump=False if a.no_bump else None,
                        style_card=style_card, layout_overrides=a.layout_overrides)
        receipt_path = di.write_receipt(run_dir, card_id)
    except (BuildError, exe.ExecutorError, OSError, ValueError, di.DesignIntelligenceError) as exc:
        print(f"REFUSED: {exc}")
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    m = request["metadata"]
    print(f"WROTE {a.out} copy_version={request['copy_version']} page_role={m['page_role']} "
          f"page_kind={m['page_kind']} stage={a.stage} "
          f"sections={m['section_count']} ids={','.join(m['canonical_ids'])}")
    cb = m["char_budget"]
    if cb["target"] and cb["min_seen"] < cb["target"]:  # floor passed (else refused); band goal missed
        print(f"WARN below the {cb['target']}-char target: shortest section {cb['min_seen']} chars; "
              "supply fuller --design-prose to reach the 95 to 100 percent band")
    lo = request.get("layout_overrides")
    if lo:
        print(f"LAYOUT-OVERRIDES file={lo['source']} sha256={lo['sha256']} stage={lo['stage']} "
              f"sections={','.join(x['section_id'] for x in lo['applied']) or 'none'}")
        for x in lo["applied"]:
            print(f"LAYOUT-OVERRIDE section {x['section_id']}: {x['appended_text']}")
            if x.get("mobile_text"):
                print(f"LAYOUT-OVERRIDE-MOBILE section {x['section_id']}: {x['mobile_text']}")
            if x.get("aspect_ratio"):
                print(f"LAYOUT-OVERRIDE-ASPECT section {x['section_id']}: {x['aspect_ratio']} ({x['viewport']})")
    print(f"CHECKED run_dir={run_dir} against={'; '.join(m['checked_against']) or 'request only'}")
    print(f"DESIGN-INTELLIGENCE receipt={receipt_path.relative_to(run_dir)} card={card_id or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
