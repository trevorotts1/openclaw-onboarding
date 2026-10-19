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
                     "{section_total}, {section_name}, at {width}px. Full colour presentation "
                     "render in the brand file's palette and type.",
    "final-mockups": "Final production mockup, section {section_number} of {section_total}, "
                     "{section_name}, at {width}px. Photographic editorial finish in the brand "
                     "file's palette and type.",
}
BLOCKS = (("notes", "LAYOUT NOTES"), ("traits", "VISUAL STANDARD TRAITS"),
          ("rules_md", "DESIGN SYSTEM, MEASURED"), ("rules_json", "DESIGN TOKENS"))
SECTION_TAIL = ("SECTION {section_number} of {section_total}: {section_name} at {width}px\n"
                "LAYOUT AND COPY:\n{copy}\nIMAGE SLOTS:\n{slots}")


# Neutral role names for the wireframe annotation. The guide's framework labels
# ("Big Bold Pain 1", "2A") are private and must never reach a public mockup.
ROLE_NAMES = {
    "1": "Opening claim", "2": "First problem", "2A": "First solution",
    "3": "Second problem", "3A": "Second solution", "4": "Third problem",
    "4A": "Third solution", "5": "Why", "6": "Who it is for", "7": "What you get",
    "8": "First benefit", "9": "Second benefit", "10": "Third benefit",
    "11": "Steps", "12": "Founder letter",
}


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
        out.append({"section_id": sid, "section_name": ROLE_NAMES[sid], "copy": copy,
                    "cta": buttons[0] if buttons else None, "slots": slots.get(sid, [])})
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


def sizes_for(request: dict, stage: str, quiet: bool = False):
    out = {}
    for index, section in enumerate(request["sections"], start=1):
        worst = 0
        for _tpl, width, _h in exe.LAYOUT[stage]:
            with contextlib.redirect_stderr(io.StringIO() if quiet else sys.stderr):
                prompt = exe.stage_prompt(stage, section, index, width, request, "3:4")
            worst = max(worst, len(prompt))
        out[section["section_id"]] = worst
    return out


def build(stage, version, manuscript_text, slots, prose, references, model, style):
    spec = json.loads((exe.SPEC_DIR / f"{version}-v6.json").read_text(encoding="utf-8"))
    sections = sections_from_manuscript(manuscript_text, spec, slots)
    request = {"model": model, "style": style, "copy_version": version,
               "references": references, "sections": sections,
               "stage_prompts": {stage: template_for(stage, {})}}
    budget = exe.prompt_budget(model)
    chosen = {}
    for key, _heading in BLOCKS:
        if not prose.get(key):
            continue
        trial = dict(chosen, **{key: prose[key]})
        request["stage_prompts"][stage] = template_for(stage, trial)
        try:
            fits = not budget or max(sizes_for(request, stage, quiet=True).values()) <= budget["target_chars"]
        except exe.ExecutorError:
            fits = False
        if fits:
            chosen = trial
    request["stage_prompts"][stage] = template_for(stage, chosen)
    sizes = sizes_for(request, stage)  # raises by section name when copy alone is over the maximum
    request["metadata"] = {
        "stage": stage, "copy_version": version, "section_count": len(sections),
        "canonical_ids": [s["section_id"] for s in sections], "provider_calls": 0,
        "dropped_blocks": [k for k, _h in BLOCKS if prose.get(k) and k not in chosen],
        "char_budget": {"target": budget and budget["target_chars"],
                        "max": budget and budget["max_chars"],
                        "min_seen": min(sizes.values()), "max_seen": max(sizes.values()),
                        "per_section": sizes},
    }
    exe.check_section_count(Path("."), request, paid=True)  # fail closed on our own output
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
    a = p.parse_args(argv)
    try:
        load = lambda f: json.loads(f.read_text(encoding="utf-8")) if f else {}
        request = build(a.stage, a.copy_version, a.manuscript.read_text(encoding="utf-8"),
                        load(a.slots), load(a.design_prose),
                        [r for r in a.references.split(",") if r], a.model, a.style)
    except (BuildError, exe.ExecutorError, OSError, ValueError) as exc:
        print(f"REFUSED: {exc}")
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    m = request["metadata"]
    print(f"WROTE {a.out} copy_version={a.copy_version} stage={a.stage} "
          f"sections={m['section_count']} ids={','.join(m['canonical_ids'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
