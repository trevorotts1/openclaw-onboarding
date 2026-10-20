#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""legacy_downsell_images.py - wireframes and mockups for EVERY page of a 3/5/7-step funnel.

(The file keeps its first name, which SKILL.md and the legacy adapter cite; it now covers all pages.)

The legacy Signature Funnel (P0..P10) has no wireframe or mockup stage. Every page of the funnel
size gets desktop wireframes, mobile wireframes and the visual mockup here, by running Skill 71's
own pipeline (build_production_request.py, then stage_executor.py); Skill 71 code is reused, never
copied. The page copy comes from the run's copy ledger, and nothing is invented to fill a gap:

  main        the 12-section signature sales page (copy form standard, page kind sales)
  upsell,     the 8-section upsell form, as page role upsell_1 / upsell_2
  upsell-2
  downsell,   the 8-section downsell structure (downsell-2 is role_instance downsell_2)
  downsell-2
  thank-you   Skill 71's 5-section thank-you page. The ledger's thank-you has three sections, so
              welcome (TY-1) fills Confirmation, what-happens-next (TY-2) fills What happens next,
              the close (TY-3) fills Help and close; Order summary and Access name the product
              only (no price, no order reference: the ledger has none). The two utility buttons
              take --access-label and --help-label.

checkout (7-step) is design-only and the legacy ledger carries no checkout copy, so it is drawn
only when the owner stages the approved five-section checkout manuscript with
--checkout-manuscript <file> ("## Section N: name" headings, the payment form named native only;
card, expiry or security-code fields are refused). Without it the receipt names the page as not
built and says what it needs. This tool never writes checkout copy.

  legacy_downsell_images.py --ledger <copy_ledger.json> --skill71-root <71 dir> \
      --brand-file <brand.json> --brand-owner <client> --out-dir <dir> [--page downsell-2]

--page narrows the run. Each page is checked against structure/page_types.json (page_set.py): a page
whose images are missing is refused. Provider is the offline stub unless --image-provider kie
--allow-paid (the review PDFs and boards are composed only on kie; the receipt lists them as render
pending). Exit 0 ok, 2 refused or a stage failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import page_set  # noqa: E402
from checkout_wrapper import CARD_FIELDS  # noqa: E402

STRUCTURE = HERE.parent / "structure" / "funnel_structure.json"
STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
# slug -> how its manuscript-built run is declared and built (the downsells use page-structures.json)
MANUSCRIPT_PAGES = {
    "main": {"intake": {"page_kind": "sales"}, "build": ["--copy-version", "standard", "--page-kind", "sales"]},
    "upsell": {"intake": {}, "build": ["--page-role", "upsell_1"]},
    "upsell-2": {"intake": {}, "build": ["--page-role", "upsell_2"]},
    "thank-you": {"intake": {"copy_version": "thank-you"}, "build": ["--copy-version", "thank-you"]},
}
NOT_BUILT = {"checkout": "design-only page: the legacy copy ledger carries no checkout copy; stage the approved "
                         "five-section checkout manuscript and re-run with --checkout-manuscript <file>"}
ROLES = ["big_bold_claim", "big_bold_pain_1", "big_bold_pain_2", "big_bold_pain_3",
         "big_bold_why", "big_bold_who", "big_bold_what", "when_time_runs_out"]


class Refused(Exception):
    pass


def _cta(label):
    return re.sub(r"^\s*CTA\s*:\s*", "", str(label or ""), flags=re.I).strip()


def _sentence(text):
    text = str(text).strip()
    return text if text[-1:] in ".!?\"')" else text + "."


def page_object(ledger_page, slug, decline_label):
    """The role's page object (Skill 81 shape) from one legacy copy-ledger page."""
    rows = ledger_page.get("sections") or []
    if [r.get("section") for r in rows] != list(range(1, 9)):
        raise Refused(f"{slug}: the copy ledger page must carry sections 1..8 in order, "
                      f"has {[r.get('section') for r in rows]}")
    first_cta = next((_cta(r.get("cta")) for r in rows if _cta(r.get("cta"))), "")
    if not first_cta:
        raise Refused(f"{slug}: no section carries a CTA label; every band has a button")
    sections = []
    for role, row in zip(ROLES, rows):
        body = [str(row.get("copy") or "").strip()]
        body += [_sentence(b) for b in row.get("bullets") or []]  # section 7 bullets
        sec = {"role": role, "body": "\n\n".join(b for b in body if b),
               # a section the ledger gave no button reuses the page's one action label
               "cta": {"label": _cta(row.get("cta")) or first_cta}}
        if role == "when_time_runs_out":
            sec["missed_out_items"] = list(row.get("items") or [])
        sections.append(sec)
    return {"page": {"sections": sections, "decline_action": {"label": decline_label}}}


def targets(structure, size, wanted, role_entries, checkout=False):
    """The matrix slugs this tool draws: every page of the funnel size except the ones named in
    NOT_BUILT (checkout joins when its manuscript is staged); a downsell page needs its entry in
    Skill 71 references/page-structures.json."""
    matrix = structure["funnel_matrix"][str(size)]
    page_types = structure["page_role_map"]["page_types"]
    found = [s for s in matrix if s in MANUSCRIPT_PAGES or page_types[s]["page_role"] in role_entries
             or (checkout and s == "checkout")]
    if wanted:
        bad = [w for w in wanted if w not in found]
        if bad:
            raise Refused(f"--page {bad}: not an image-staged page of the {size}-step funnel {found}")
        return [w for w in found if w in wanted]
    return found


def manuscript_section(row, sid):
    """One ledger section as a manuscript section: copy, bullets, numbered steps or items, the
    heartfelt-letter parts and the CTA button, with a full stop on every list line."""
    out = [f"## Section {sid}: {row.get('name') or ''}", ""]
    if row.get("copy"):
        out += [str(row["copy"]).strip(), ""]
    out += [f"- {_sentence(b)}" for b in row.get("bullets") or []]
    out += [f"{n}. {_sentence(t)}" for n, t in enumerate((row.get("steps") or []) + (row.get("items") or []), 1)]
    for n, part in enumerate(row.get("parts") or [], 1):
        out += ["", f"### Part {n}: {part['label']}", "", str(part["text"]).strip()]
    if _cta(row.get("cta")):
        out += ["", f"**[CTA BUTTON: {_cta(row['cta'])}]**"]
    return out + ["", "---", ""]


def manuscript_for(slug, ledger_page, args, product_title):
    """The page's manuscript text for Skill 71's request builder; refuses a section list that is not
    the one the page type carries."""
    rows = ledger_page.get("sections") or []
    got = [str(r.get("section")) for r in rows]
    if slug == "thank-you":
        if got != ["TY-1", "TY-2", "TY-3"]:
            raise Refused(f"{slug}: the copy ledger page must carry sections TY-1, TY-2, TY-3 in order, has {got}")
        welcome, steps, close = rows
        if not steps.get("steps"):
            raise Refused(f"{slug}: TY-2 carries no steps")
        title = str(product_title).strip().rstrip(".!?")
        if not title:
            raise Refused(f"{slug}: the copy ledger carries no product_title for the order summary")
        return "\n".join([
            "## Section 1: Confirmation and welcome", "", _sentence(welcome["copy"]), "",
            f"**[CTA BUTTON: {args.access_label}]**", "", "---", "",
            "## Section 2: Order summary", "", f"{title}. Paid.", "", "---", "",
            "## Section 3: Access", "", f"{title}.", "", f"**[CTA BUTTON: {args.access_label}]**", "", "---", "",
            "## Section 4: What happens next", "",
            *[f"{n}. {_sentence(t)}" for n, t in enumerate(steps["steps"], 1)], "", "---", "",
            "## Section 5: Help, manage and close", "", _sentence(close["copy"]), "",
            f"**[CTA BUTTON: {args.help_label}]**", ""])
    want = [str(n) for n in range(1, 13 if slug == "main" else 9)]
    if got != want:
        raise Refused(f"{slug}: the copy ledger page must carry sections {want[0]}..{want[-1]} in order, has {got}")
    return "\n".join(line for row in rows for line in manuscript_section(row, row["section"]))


def draw(run, build_args, args, scripts):
    """The three stages through Skill 71's own builder and executor, in the run folder."""
    model = args.image_model or ("STUB-NO-MODEL" if args.image_provider == "stub"
                                 else "gpt-image-2-5-sunburst-image-to-image")
    py = sys.executable
    for stage in STAGES:
        build = [py, str(scripts / "build_production_request.py"), *build_args, "--stage", stage,
                 "--model", model, "--out", f"production-request-{stage}.json", "--run-dir", "."]
        if args.design_prose:
            build += ["--design-prose", str(args.design_prose.resolve())]
        execute = [py, str(scripts / "stage_executor.py"), ".", "--request",
                   f"production-request-{stage}.json", "--stages", stage,
                   "--provider", args.image_provider]
        if args.image_provider == "kie":
            execute.append("--allow-paid")
        for cmd in (build, execute):
            proc = subprocess.run(cmd, cwd=run, capture_output=True, text=True)
            if proc.returncode != 0:
                tail = (proc.stdout + proc.stderr).strip().splitlines()[-8:]
                raise Refused(f"{run.name}: {Path(cmd[1]).name} {stage} exited {proc.returncode}: " + " | ".join(tail))


def run_page(slug, structure, ledger, args, scripts, entries):
    run = args.out_dir / slug
    run.mkdir(parents=True, exist_ok=True)
    ledger_page = {p.get("page_type"): p for p in ledger.get("pages") or []}.get(slug)
    if ledger_page is None and slug != "checkout":  # checkout copy is the staged manuscript, not the ledger
        raise Refused(f"{slug}: the copy ledger has no such page")
    entry = structure["page_role_map"]["page_types"][slug]
    role = entry["page_role"]
    # page_role in the intake is what names every file the page makes (deliverable_labels.py)
    intake = {"brand_owner": args.brand_owner, "brand_file": str(args.brand_file.resolve()), "page_role": role}
    if entry.get("role_instance"):  # downsell-2: every file is labelled Downsell 2
        intake["role_instance"] = entry["role_instance"]
    if slug == "checkout":
        text = args.checkout_manuscript.read_text(encoding="utf-8")
        if CARD_FIELDS.search(text):
            raise Refused("checkout: the manuscript names card, expiry or security-code fields; the payment "
                          f"form is the native checkout form only ({CARD_FIELDS.search(text).group(0)!r})")
        manuscript = run / "copy" / "internal-manuscript.md"
        manuscript.parent.mkdir(parents=True, exist_ok=True)
        manuscript.write_text(text, encoding="utf-8")
        build_args = ["--manuscript", str(manuscript), "--page-role", role]
    elif slug in MANUSCRIPT_PAGES:
        cfg = MANUSCRIPT_PAGES[slug]
        manuscript = run / "copy" / "internal-manuscript.md"
        manuscript.parent.mkdir(parents=True, exist_ok=True)
        manuscript.write_text(manuscript_for(slug, ledger_page, args, ledger.get("product_title") or ""),
                              encoding="utf-8")
        intake.update(cfg["intake"])
        build_args = ["--manuscript", str(manuscript), *cfg["build"]]
    else:
        copy = run / "page-copy.json"
        copy.write_text(json.dumps(page_object(ledger_page, slug, args.decline_label), indent=2) + "\n",
                        encoding="utf-8")
        build_args = ["--page-role", role, "--page-copy", str(copy)]
    (run / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
    draw(run, build_args, args, scripts)
    out = {}
    for stage in STAGES:
        record = run / stage / "stage-executor-record.json"
        if not record.is_file():
            raise Refused(f"{slug}: stage {stage} wrote no record at {record}")
        rec = json.loads(record.read_text(encoding="utf-8"))
        out[stage] = {"record": str(record), "sha256": hashlib.sha256(record.read_bytes()).hexdigest(),
                      "images": len(rec.get("images") or [])}
    key = page_set.page_key_for_slug(slug)
    check = page_set.check_deliverables(key, run, rendered=False)
    if check["missing"]:  # planned versus delivered: a page missing its images is not delivered
        raise Refused(f"{slug}: the run folder is missing {check['missing']}; the page is not delivered")
    return {"run_dir": str(run), "page_role": role, "page_key": key, "stages": out,
            "render_pending": check["render_pending"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ledger", type=Path, required=True, help="the run's copy_ledger.json")
    ap.add_argument("--skill71-root", type=Path, required=True)
    ap.add_argument("--brand-file", type=Path, required=True)
    ap.add_argument("--brand-owner", required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--page", action="append", help="a matrix slug to build (repeatable)")
    ap.add_argument("--checkout-manuscript", type=Path,
                    help="the approved five-section checkout manuscript; without it checkout is reported not built")
    ap.add_argument("--decline-label", default="No thanks",
                    help="the decline button label of the downsell pages (the legacy ledger carries none)")
    ap.add_argument("--access-label", default="Access Your Purchase",
                    help="the thank-you page's access button label (the legacy ledger carries none)")
    ap.add_argument("--help-label", default="Get Support",
                    help="the thank-you page's help button label (the legacy ledger carries none)")
    ap.add_argument("--image-provider", choices=["stub", "kie"], default="stub")
    ap.add_argument("--allow-paid", action="store_true")
    ap.add_argument("--image-model")
    ap.add_argument("--design-prose", type=Path)
    args = ap.parse_args(argv)
    try:
        if args.image_provider == "kie" and not args.allow_paid:
            raise Refused("--image-provider kie spends money; it needs --allow-paid, approved by the owner")
        root = args.skill71_root.resolve()
        scripts = root / "scripts"
        entries_file = root / "references" / "page-structures.json"
        for need in (scripts / "build_production_request.py", scripts / "stage_executor.py", entries_file):
            if not need.is_file():
                raise Refused(f"the Skill 71 tree lacks {need}")
        entries = json.loads(entries_file.read_text(encoding="utf-8"))["roles"]
        ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
        structure = json.loads(STRUCTURE.read_text(encoding="utf-8"))
        size = ledger.get("funnel_size")
        if str(size) not in structure["funnel_matrix"]:
            raise Refused(f"copy ledger funnel_size {size!r} is not 3, 5 or 7")
        if args.checkout_manuscript and not args.checkout_manuscript.is_file():
            raise Refused(f"--checkout-manuscript {args.checkout_manuscript} is not a file")
        slugs = targets(structure, size, args.page, entries, bool(args.checkout_manuscript))
        report = {"funnel_size": size, "pages": {},
                  "not_built": {s: NOT_BUILT[s] for s in structure["funnel_matrix"][str(size)]
                                if s in NOT_BUILT and not (s == "checkout" and args.checkout_manuscript)}}
        for slug in slugs:
            report["pages"][slug] = run_page(slug, structure, ledger, args, scripts, entries)
        report["note"] = ("the image inventory, generation, Design Board approval and final-mockups "
                          "are client-gated stages downstream and were not run")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "page-images-receipt.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except (Refused, OSError, ValueError, KeyError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
