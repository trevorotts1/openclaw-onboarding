#!/usr/bin/env python3
"""Design styles A Block, B Circle, C Hybrid: the data the code reads (Skill 71).

Definitions live in references/design-styles.md (prose) and references/design-styles.json (data).
This module loads the data and answers four questions for the other scripts:

  slot_shape(slot)                  "rect" or "circle" for one slot dict
  slot_failures(style, slots)       named reasons a style refuses a slot list
  style_block(style, stage, slots)  the block stage_executor adds to a stage prompt
  board_block(style, slots)         the fields the Design Board stage prints for the style
  board_prompt_block(style, slots)  the paragraph the Design Board prompt carries for the style

CLI:
  design_style.py question                 print the intake question with the example links
  design_style.py validate REQUEST.json    check production-request.json slot shapes (and the sibling
                                           desktop-wireframe/image-inventory.json when present) against its style
  design_style.py validate-inventory RUN_DIR   check desktop-wireframe/image-inventory.json against intake.json's
                                           style (the file that drives circle generation); a gate validator
  design_style.py board-block A|B|C        print the Design Board fields as JSON
Exit 0 pass, 1 failures, 2 unreadable input.
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "references" / "design-styles.json"
STYLE_IDS = ("A", "B", "C")
WIREFRAME_STAGES = ("desktop-wireframe", "mobile-tablet")


def load(path=DATA):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def style(style_id, data=None):
    data = data or load()
    for entry in data["styles"]:
        if entry["id"] == style_id:
            return entry
    raise ValueError(f"unknown design style {style_id!r}; expected one of {list(STYLE_IDS)}")


def slot_shape(slot):
    """A slot's delivered shape. `mask: circle` (composition library) is the same as shape."""
    value = slot.get("shape") or slot.get("mask") or "rect"
    return value


def _slot_id(slot, i):
    return slot.get("slot_id") or slot.get("id") or f"slot[{i}]"


def slot_failures(style_id, slots):
    """Named failures for one style and a flat list of slot dicts; empty means pass."""
    entry = style(style_id)
    out, circles = [], []
    for i, slot in enumerate(slots, start=1):
        shape, sid = slot_shape(slot), _slot_id(slot, i)
        if shape not in ("rect", "circle"):
            out.append(f"{sid}: shape {shape!r} is not rect or circle")
            continue
        if shape == "circle":
            circles.append(sid)
            ratio = slot.get("aspect_ratio") or slot.get("intended_ratio") or slot.get("ratio")
            if ratio not in (None, "1:1"):
                out.append(f"{sid}: a circle slot must be generated square (1:1), not {ratio}")
            ring = slot.get("ring")
            if ring is not None and not (isinstance(ring, dict) and ring.get("color")):
                out.append(f"{sid}: a ring needs a client brand color (#RRGGBB); there is no default")
    if circles and entry["circle_slots"] == "forbidden":
        out.append(f"Style {style_id} ({entry['name']}) uses rectangular photos only; "
                   f"circle slot(s) {', '.join(circles)} are not allowed")
    if style_id == "C" and circles and len(circles) > max(1, len(slots) // 3):
        out.append(f"Style C allows circle accents on at most one in three photo slots; "
                   f"{len(circles)} of {len(slots)} are circle ({', '.join(circles)}). "
                   "A page that is mostly circles is Style B")
    return out


def circle_clause(data=None):
    return (data or load())["circle_clause"]


def style_block(style_id, stage, slots, data=None):
    """The prompt block for one stage and one section's slots."""
    data = data or load()
    entry = style(style_id, data)
    rules = entry["prompt_rules"]
    phase = rules["wireframe" if stage in WIREFRAME_STAGES else "mockup"]
    parts = [rules["all"], phase]
    circles = [_slot_id(s, i) for i, s in enumerate(slots, start=1) if slot_shape(s) == "circle"]
    if circles:
        parts.append("Circle slots in this section: " + ", ".join(circles) + ".")
    return " ".join(parts)


def board_block(style_id, slots=(), data=None):
    entry = style(style_id, data)
    return {"design_style": {
        "id": entry["id"], "name": entry["name"], "one_line": entry["one_line"],
        "circle_slot_ids": [_slot_id(s, i) for i, s in enumerate(slots, start=1)
                            if slot_shape(s) == "circle"]}}


def board_prompt_block(style_id, slots=(), data=None):
    """One paragraph for the Design Board prompt: the chosen style and how the imagery grid
    draws each slot (circle tiles for circle slots, rectangles for the rest)."""
    entry = style(style_id, data)
    circles = [_slot_id(s, i) for i, s in enumerate(slots, start=1) if slot_shape(s) == "circle"]
    grid = (f"circle slots ({', '.join(circles)}) are drawn as circular tiles with a thin ring in the "
            "client's accent color and every other slot as a rectangle" if circles
            else "every image slot is drawn as a rectangle")
    return (f"DESIGN STYLE — Style {entry['id']} {entry['name']}: {entry['one_line']} In the imagery "
            f"grid {grid}. The style governs shape and layout only; every color is the client's.")


def question_text(data=None):
    data = data or load()
    q = data["question"]
    lines = [q["intro"], ""]
    for entry in data["styles"]:
        ex = entry["example"]
        lines.append(f"{entry['id']}. {entry['name']}: {entry['one_line']}")
        if ex.get("url"):
            lines.append(f"   See it: {ex['url']}")
            if ex.get("mobile_url"):
                lines.append(f"   On a phone: {ex['mobile_url']}")
        else:
            lines.append("   No example picture yet; it is A's layout with B's round photos on the "
                         "personal pictures. A and B above show its two ingredients.")
        lines.append("")
    lines.append(q["closing"])
    return "\n".join(lines)


def inventory_slots(path):
    """The entry dicts of an image-inventory.json, whichever dialect list key it uses."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else (
        data.get("images") or data.get("items") or data.get("inventory") or [])
    return [item for item in items if isinstance(item, dict)]


def _request_slots(request):
    for section in request.get("sections") or []:
        yield from (section.get("slots") or [])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["question"]:
        print(question_text())
        return 0
    if len(argv) == 2 and argv[0] == "board-block":
        try:
            print(json.dumps(board_block(argv[1]), indent=2))
        except ValueError as exc:
            print(f"FAIL: {exc}")
            return 2
        return 0
    if len(argv) == 2 and argv[0] == "validate":
        try:
            request = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
            style_id = request.get("design_style")
            intake = Path(argv[1]).parent / "intake.json"   # same fallback the executor uses
            if not style_id and intake.is_file():
                style_id = json.loads(intake.read_text(encoding="utf-8")).get("design_style")
            if style_id not in STYLE_IDS:
                print(f"FAIL: request design_style {style_id!r} is not one of {list(STYLE_IDS)}")
                return 1
            failures = slot_failures(style_id, list(_request_slots(request)))
            inventory = Path(argv[1]).parent / "desktop-wireframe" / "image-inventory.json"
            if inventory.is_file():   # the inventory drives circle generation; check it too
                failures += [f"image inventory: {f}" for f in slot_failures(style_id, inventory_slots(inventory))]
        except (OSError, ValueError) as exc:
            print(f"FAIL: {exc}")
            return 2
        if failures:
            print(f"FAIL: Style {style_id} slot shapes")
            for line in failures:
                print(f"- {line}")
            return 1
        print(f"PASS: Style {style_id} slot shapes")
        return 0
    if len(argv) == 2 and argv[0] == "validate-inventory":
        run_dir = Path(argv[1])
        try:
            intake = json.loads((run_dir / "intake.json").read_text(encoding="utf-8"))
            style_id = intake.get("design_style") if isinstance(intake, dict) else None
            inventory = run_dir / "desktop-wireframe" / "image-inventory.json"
            if not style_id:   # test runs and older runs carry no style; gate:intake_design_style owns that
                print("PASS: intake.json records no design_style; no slot-shape rule applies")
                return 0
            if style_id not in STYLE_IDS:
                print(f"FAIL: intake design_style {style_id!r} is not one of {list(STYLE_IDS)}")
                return 1
            failures = slot_failures(style_id, inventory_slots(inventory))
        except (OSError, ValueError) as exc:
            print(f"FAIL: {exc}")
            return 2
        if failures:
            print(f"FAIL: Style {style_id} image inventory slot shapes")
            for line in failures:
                print(f"- {line}")
            return 1
        print(f"PASS: Style {style_id} image inventory slot shapes")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
