#!/usr/bin/env python3
"""UPS-20 - the per-section image plan of the upsell page.

Skill 71's builder (build_production_request.py) falls back to a heading-derived
art direction ("Editorial photograph that illustrates: <heading>") for any upsell
section it is given no plan for. That is a stock-style picture with no tie to the
offer, and U2 would look like U1. This module writes the plan the builder takes
with --slots: for each of the eight sections one slot carrying a subject, a
composition and an offer-specific art direction, from the offer record and,
when given, the brand visual bible. U1 and U2 have their own plan text.

    python3 upsell_image_plan.py --request <request.json> [--visual-bible <vb.json>] \
        --out slots.json
    build_production_request.py ... --slots slots.json

slots.json: {"<section id>": [{"slot_id", "aspect_ratio", "art_direction",
"subject", "composition"}]}. Slot ids and ratios come from the role's entry in
71-blackceo-signature-page/references/page-structures.json `layouts`, so the
plan and the band geometry cannot drift apart. No claim, result or testimonial
is ever invented: a plan describes a scene, never an outcome.

visual bible (optional JSON): {"world": setting, "look": grade or style,
"casting": who appears, "avoid": [extra things to keep out of frame]}.
"""
import argparse
import json
import sys
from pathlib import Path

STRUCTURES = (Path(__file__).resolve().parents[3] / "71-blackceo-signature-page"
              / "references" / "page-structures.json")
ALWAYS_AVOID = ["stock handshakes", "floating icons", "readable text", "logos", "invented results"]

# section id -> (label, subject, composition). {offer} is the offer's display name, {item}
# one of its deliverables (cycled by section), {items} up to three of them. The label is the
# first clause: the wireframe prints it on the image plate, so it stays short.
U1 = {
    "1": ("{offer} as the one added thing",
          "the {offer} shown as a finished, ready-to-use extra, with {item} as the hero detail",
          "wide hero frame, subject on the right third, calm negative space on the left for the headline"),
    "2": ("the gap after the main purchase",
          "one person alone with their work after the main purchase, the quiet moment that {item} picks up",
          "candid medium shot from over the shoulder, shallow depth of field, subject in the right third"),
    "3": ("the same work done twice",
          "a workspace mid-task, drafts and notes spread out, effort repeated without a system",
          "wide level frame at a three-quarter angle, empty centre so the statement can sit over it"),
    "4": ("the decision still open",
          "a thoughtful person at a decision point, no prop that implies a result",
          "tight side-lit portrait, quiet dark background, subject centred so a card can overlap an edge"),
    "5": ("why this extra exists",
          "the maker's hands preparing {item}, honest and unposed",
          "medium close-up at eye level, subject left of the statement"),
    "6": ("the person this fits",
          "a relaxed ideal buyer in their own working space, at ease, an invitation and never a judgement",
          "square crop, head and shoulders in a natural setting, safe for a circular mask"),
    "7": ("everything added, laid out",
          "the {offer} deliverables laid out as physical or on-screen objects: {items}",
          "overhead flat-lay on an ordered grid, brand-colour accents, no lettering on the objects"),
    "8": ("the next step, resolved",
          "an ordinary working day made calmer by {offer}, nothing staged",
          "wide closing frame in warm light, the subject small inside a generous scene"),
}
U2 = {
    "1": ("the next level of {offer}",
          "the {offer} as the step beyond what the buyer already owns, {item} in use by a practised hand",
          "cinematic wide frame from a low angle, subject left of centre, deep space on the right"),
    "2": ("the ceiling of the first result",
          "a skilled person pausing at the limit of what they have, {item} just out of reach on the table",
          "close two-shot at desk height, strong foreground object, subject in the left third"),
    "3": ("the plateau",
          "a long unchanged routine shown as the same desk at three different times of day",
          "triptych-style wide frame, even horizontal rhythm, space in the middle for the statement"),
    "4": ("the missing piece",
          "an almost-complete setup with one visible gap where {item} belongs",
          "macro detail on the gap, shallow focus, dark ground so a card can overlap the plate edge"),
    "5": ("why now, not later",
          "the builder at the bench with a calendar and the work in progress, deliberate and unhurried",
          "high three-quarter view from above, subject right of the statement"),
    "6": ("the person ready for more",
          "an experienced practitioner mid-stride in their own environment, composed and curious",
          "square crop, waist-up and in motion, safe for a circular mask"),
    "7": ("what the upgrade adds",
          "the added parts of {offer} set beside the original kit: {items}",
          "side-by-side still life on a pale surface, brand-colour accents, no lettering on the objects"),
    "8": ("the decision, made",
          "a finished, polished workspace at dusk where {offer} is part of the routine",
          "wide closing frame in cool evening light, subject small and off-centre"),
}
PLANS = {"upsell_1": U1, "upsell_2": U2}


class PlanError(ValueError):
    pass


def _layout(instance, structures):
    try:
        data = json.loads(Path(structures).read_text(encoding="utf-8"))
        return {s["id"]: s for s in data["layouts"][instance]["sections"]}
    except (OSError, ValueError, KeyError) as exc:
        raise PlanError("cannot read the %s layout from %s: %s" % (instance, Path(structures).name, exc))


def build_slots(request, visual_bible=None, structures=STRUCTURES):
    """The --slots object for one upsell request (its `instance` or `page_role`)."""
    instance = request.get("instance") or request.get("page_role")
    if instance not in PLANS:
        raise PlanError("instance %r is not one of %s" % (instance, sorted(PLANS)))
    offer = request.get("offer") or {}
    name = str(offer.get("display_name") or "").strip()
    if not name:
        raise PlanError("the offer record carries no display_name; the plan is built from the offer, never invented")
    items = [str(d).strip() for d in offer.get("deliverables") or [] if str(d).strip()] or [name]
    bible = visual_bible or {}
    tail = []
    if bible.get("look"):
        tail.append("look: %s" % str(bible["look"]).strip())
    if bible.get("world"):
        tail.append("setting: %s" % str(bible["world"]).strip())
    if bible.get("casting"):
        tail.append("cast: %s" % str(bible["casting"]).strip())
    tail.append("never: %s" % ", ".join(ALWAYS_AVOID + [str(a).strip() for a in bible.get("avoid") or []]))
    layout = _layout(instance, structures)
    out = {}
    for n, (sid, (label, subject, composition)) in enumerate(PLANS[instance].items()):
        fill = {"offer": name, "item": items[n % len(items)], "items": ", ".join(items[:3])}
        label, subject, composition = (x.format(**fill) for x in (label, subject, composition))
        slot = layout[sid]["slot"]
        out[sid] = [{"slot_id": slot["slot_id"], "aspect_ratio": slot["aspect_ratio"],
                     "art_direction": "; ".join([label, subject, composition] + tail),
                     "subject": subject, "composition": composition}]
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Write the upsell image plan (--slots file)")
    p.add_argument("--request", required=True)
    p.add_argument("--visual-bible")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    load = lambda f: json.loads(Path(f).read_text(encoding="utf-8"))
    try:
        slots = build_slots(load(a.request), load(a.visual_bible) if a.visual_bible else None)
    except (PlanError, OSError, ValueError) as exc:
        print("REFUSED: %s" % exc)
        return 1
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(slots, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote %s (%d sections)" % (a.out, len(slots)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
