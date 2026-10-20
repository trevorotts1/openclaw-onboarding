#!/usr/bin/env python3
"""emit_section_manuscript.py - Skill 78 page copy as Skill 71's five-section manuscript.

Turns an approved selection plan (build_selection_plan.py output) into the
manuscript and manifest Skill 71's image pipeline reads for the order page
(copy form `product-selection`, 71 references/copy-specs/product-selection-v1.json):

  Section 1  Bridge headline        Section 4  Compare (comparison rows)
  Section 2  How to choose          Section 5  Questions and trust
  Section 3  Packages (one card per approved offer, one Choose button each)

Every fact comes from the plan: names, buyers, outcomes, inclusions, exclusions,
exact prices and terms, the comparison matrix, the published recommendation, the
FAQ and trust items. Nothing is invented. Two sentences have no plan field and are
either authored (--copy copy.json: {"bridge_headline", "how_to_choose"}) or derived
from the plan's own matrix; the manifest records which. Section 5 falls back to the
plan's own no-payment fact when the plan carries no FAQ or trust item.

Writes <run_dir>/copy/internal-manuscript.md and <run_dir>/copy/copy-manifest.json.
No provider call, no network.

Usage:
  emit_section_manuscript.py <plan.json> --run-dir <dir> [--copy copy.json]
  emit_section_manuscript.py --self-test
Exit: 0 written, 3 fail-closed error.
"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402
from render_selection_preview import price_line  # noqa: E402

STATE = {"included": "Included", "not_included": "Not included", "limited": "Limited", "conditional": "Conditional"}
SECTION_NAMES = {"1": "Bridge headline", "2": "How to choose", "3": "Packages", "4": "Compare",
                 "5": "Questions and trust"}


def _end(text):
    text = str(text).strip()
    return text if text[-1:] in ".!?" else text + "."


def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _item(e):
    return e.get("item") if isinstance(e, dict) else e


def derived_paragraph(plan):
    matrix = plan["comparison_matrix"]
    names = [matrix["offer_names"][o] for o in matrix["offer_ids_in_order"]]
    same = [r["dimension_item"] for r in matrix["rows"] if set(r["cells"].values()) == {"included"}]
    differ = [r["dimension_item"] for r in matrix["rows"] if len(set(r["cells"].values())) > 1]
    text = f"There are {len(names)} packages to choose from: {_join(names)}."
    if same:
        text += f" Every package includes {_join(same)}."
    if differ:
        text += f" They differ in {_join(differ)}."
    return text


def card(offer, rec):
    lines = [f"### Package: {offer['display_name']}", offer["display_name"]]
    if offer.get("intended_buyer"):
        lines.append(_end(f"Best for: {offer['intended_buyer']}"))
    if offer.get("primary_outcome"):
        lines.append(_end(offer["primary_outcome"]))
    bullets = [f"- {d}" for d in offer.get("deliverables", [])]
    for e in offer.get("limited_deliverables", []):
        note = f" ({e['note']})" if isinstance(e, dict) and e.get("note") else ""
        bullets.append(f"- {_item(e)}{note}, limited")
    for e in offer.get("conditional_deliverables", []):
        cond = f" ({e['condition']})" if isinstance(e, dict) and e.get("condition") else ""
        bullets.append(f"- {_item(e)}{cond}, conditional")
    bullets += [f"- Not included: {x}" for x in offer.get("exclusions", [])]
    # one approved price per card here; a second schedule choice is a control inside the card (UI contract)
    prices = [html.unescape(price_line(p)) for p in offer.get("prices", [])]
    body = lines[1:] + bullets + ([_end(" or ".join(prices))] if prices else [])
    out = [lines[0], ""]
    for text in body:
        out += [text, ""]
    if rec and rec.get("placement") == "published" and rec.get("offer_id") == offer["offer_id"]:
        reason = str(rec["reason"])
        out += [_end(reason if reason.lower().startswith("recommended") else f"Recommended: {reason}"), ""]
    out += [f"[CTA BUTTON: {offer['cta']}]", ""]
    return out


def build(plan, authored=None):
    """(manuscript_text, manifest) for a plan whose outcome is 'plan'."""
    if plan.get("outcome") != "plan":
        raise ValueError(f"the plan outcome is {plan.get('outcome')!r}; a selection page is built only from a 'plan'")
    authored = authored or {}
    matrix = plan["comparison_matrix"]
    names = matrix["offer_names"]
    headline = authored.get("bridge_headline") or "Thanks for your interest. Choose the package that fits you."
    paragraph = authored.get("how_to_choose") or derived_paragraph(plan)
    md = ["# Selection page manuscript", "", f"## Section 1: {SECTION_NAMES['1']}", "", _end(headline), "",
          f"## Section 2: {SECTION_NAMES['2']}", "", _end(paragraph), "",
          f"## Section 3: {SECTION_NAMES['3']}", ""]
    for offer in plan["offers_in_order"]:
        md += card(offer, plan.get("recommendation"))
    md += [f"## Section 4: {SECTION_NAMES['4']}", ""]
    for row in matrix["rows"]:
        cells = []
        for oid in matrix["offer_ids_in_order"]:
            note = (row.get("notes") or {}).get(oid)
            cells.append(f"{names[oid]} {STATE[row['cells'][oid]].lower()}" + (f" ({note})" if note else ""))
        md += [f"- {row['dimension_item']}: " + "; ".join(cells) + ".", ""]
    for e in matrix.get("exclusions", []):
        md += [f"- Not included, {names.get(e['offer_id'], e['offer_id'])}: {_end(e['exclusion'])}", ""]
    md += [f"## Section 5: {SECTION_NAMES['5']}", ""]
    faq, trust = plan.get("faq") or [], list(plan.get("trust_items") or [])
    for f in faq:
        question = str(f["question"]).strip()
        md += [question if question.endswith("?") else _end(question), "", _end(f["answer"]), ""]
    if not faq and not trust and plan.get("ui_model", {}).get("collects_payment") is False:
        trust = ["This page collects no payment details"]  # the plan's own ui_model fact
    for t in trust:
        md += [f"- {_end(t)}", ""]
    manifest = {"copy_version": "product-selection", "page_role": "product_selection",
                "sections": list(SECTION_NAMES), "offer_ids": [o["offer_id"] for o in plan["offers_in_order"]],
                "button_labels": [o["cta"] for o in plan["offers_in_order"]],
                "authored": {"bridge_headline": "bridge_headline" in authored,
                             "how_to_choose": "how_to_choose" in authored},
                "source": "selection plan " + str(plan.get("launch_id"))}
    return "\n".join(md).rstrip() + "\n", manifest


def write(plan_path, run_dir, copy_path=None):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    authored = json.loads(Path(copy_path).read_text(encoding="utf-8")) if copy_path else None
    text, manifest = build(plan, authored)
    out = Path(run_dir) / "copy"
    out.mkdir(parents=True, exist_ok=True)
    (out / "internal-manuscript.md").write_text(text, encoding="utf-8")
    (out / "copy-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out / "internal-manuscript.md", out / "copy-manifest.json"


def self_test():
    plan = build_plan(SELF_TEST_LAUNCH, {"offer_id": "MAIN-B", "reason": "Recommended for founders who need individual feedback", "approved": True})
    text, manifest = build(plan)
    assert [l for l in text.splitlines() if l.startswith("## Section")] == [
        f"## Section {i}: {n}" for i, n in SECTION_NAMES.items()], text
    assert text.count("[CTA BUTTON:") == 2 and "[CTA BUTTON: Choose TEST ONLY A]" in text
    assert "$97.00, one time." in text and "Not included: No private reviews" in text
    assert "\nRecommended for founders who need individual feedback.\n" in text
    assert "Two private review sessions: TEST ONLY A not included; TEST ONLY B included." in text
    assert "This page collects no payment details." in text
    assert manifest["sections"] == ["1", "2", "3", "4", "5"] and manifest["button_labels"][1] == "Choose TEST ONLY B"
    try:
        build({"outcome": "declined_single_offer"})
    except ValueError:
        pass
    else:
        raise AssertionError("a declined plan was not refused")
    print("emit_section_manuscript --self-test: PASS (five sections, one button per package, exact price and exclusions, matrix rows, no invented fact)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = lambda n: argv[argv.index(n) + 1] if n in argv else None
    if not args or not opt("--run-dir"):
        print("usage: emit_section_manuscript.py <plan.json> --run-dir <dir> [--copy copy.json]", file=sys.stderr)
        return 3
    try:
        paths = write(args[0], opt("--run-dir"), opt("--copy"))
    except Exception as e:  # fail closed
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 3
    print("wrote " + " and ".join(str(p) for p in paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
