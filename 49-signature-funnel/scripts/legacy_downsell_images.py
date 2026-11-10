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

Before a page is drawn, every section funnel_structure.json image_coverage requires an image for gets a slot in the
page's own production request (the stricter rule wins over Skill 71's type-only sections), and the wireframe
section-plan.json and image-inventory.json are written from that request.

After Skill 71's client-gated path has closed final-mockups for each page (Design Board approval first),
--record-final-mockups --out-dir <dir> draws nothing and spends nothing: it reads each page's closed
final-mockups/stage-executor-record.json, merges {record, sha256, images} into page-images-receipt.json, and
exits 2 naming any page whose record is missing or carries no images (then the receipt is left as it was).
A record changed after that is caught by the P7 build gate on the sha256.

--page narrows the run. Each page is checked against structure/page_types.json (page_set.py): a page
whose images are missing is refused. Provider DEFAULTS to kie (--allow-paid required); the offline stub
is opt-in only and needs a recorded owner approval, --stub-approved-by <ref> (the review PDFs and boards
are composed only on kie; the receipt lists them as render pending). Exit 0 ok, 2 refused or a stage failed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import page_set  # noqa: E402
import prove_sf_prompt_floor as psf  # noqa: E402  (the one source of the required per-section image set)
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


def _image_model(args):
    """The image-to-image model every page is drawn with, resolved through Skill 66 (IMG-19): the
    --image-model override, the stub's placeholder, else Skill 66's own selector. Never a literal id."""
    if args.image_model:
        return args.image_model
    if args.image_provider == "stub":
        return "STUB-NO-MODEL"
    path = Path(__file__).resolve().parents[2] / "shared-utils" / "signature_launch" / "image_model.py"
    try:
        spec = importlib.util.spec_from_file_location("signature_launch_image_model", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.resolve()
    except Exception as exc:  # ImageModelError, a missing file, a broken Skill 66 tree
        raise Refused(f"images: Skill 66 did not resolve the image-to-image model ({exc}); nothing is drawn")


IMG_ID = re.compile(r"^IMG-\d+$")


def required_sections(slug, size):
    """The numbered sections of this page that funnel_structure.json image_coverage says carry one
    image (the stricter rule: Skill 71 marks some sections type-only, the funnel structure still
    requires an image there, and prove_sf_build binds the wireframe inventory to this set)."""
    pairs = psf.required_image_pairs(size, psf.load_structure())
    return {str(sec) for page, sec in pairs if page == slug and sec != psf.ANY_IMAGE}


def bind_slots(run, request_name, required, bands):
    """Make the page's own production request carry a slot in every required section, then write the
    wireframe plan and inventory from it. A required section the request left without a slot gets one
    before any draw (the band's declared slot ratio when the page type declares bands, else 16:9);
    IMG-NNN ids are renumbered in section order so they stay unique. Idempotent for one page: the
    three stage requests are the same sections, so each gets the same slots and ids.
    Returns (section plan, inventory entries)."""
    path = run / request_name
    request = json.loads(path.read_text(encoding="utf-8"))
    sections = request.get("sections") or []
    for sec in sections:
        sid = str(sec.get("section_id"))
        if sid in required and not sec.get("slots"):
            sec["slots"] = [{"slot_id": "IMG-000", "aspect_ratio": (bands.get(sid) or {}).get("aspect_ratio") or "16:9",
                             "art_direction": f"Editorial photograph that illustrates: {sec.get('section_name') or 'this section'}"}]
    n = 0
    for sec in sections:
        for slot in sec.get("slots") or []:
            if IMG_ID.match(str(slot.get("slot_id"))):
                n += 1
                slot["slot_id"] = f"IMG-{n:03d}"
    path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    plan = [{"section_id": str(sec.get("section_id")),
             "image_slot_ids": [str(sl["slot_id"]) for sl in sec.get("slots") or []]} for sec in sections]
    inventory = [{"id": str(sl["slot_id"]), "section_id": str(sec.get("section_id")), **sl}
                 for sec in sections for sl in sec.get("slots") or []]
    return plan, inventory


def draw(run, build_args, args, scripts, required=frozenset(), bands=None):
    """The three stages through Skill 71's own builder and executor, in the run folder.
    args.image_model is already resolved (main, once per run)."""
    model = args.image_model
    py = sys.executable
    for stage in STAGES:
        build = [py, str(HERE / "build_production_request_with_layouts.py"), str(scripts), *build_args, "--stage", stage,
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
            if cmd is build:  # slots are bound before the stage draws, never after
                plan, inventory = bind_slots(run, f"production-request-{stage}.json", required, bands or {})
                if stage in ("desktop-wireframe", "mobile-tablet"):
                    (run / stage).mkdir(exist_ok=True)
                    (run / stage / "section-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
                if stage == "desktop-wireframe":
                    (run / stage / "image-inventory.json").write_text(
                        json.dumps({"images": inventory}, indent=2) + "\n", encoding="utf-8")


def record_final_mockups(out_dir):
    """--record-final-mockups: no draw, no spend. Merge each receipt page's closed final-mockups record
    ({record, sha256, images}) into page-images-receipt.json; refuse, writing nothing, if any page lacks one."""
    path = out_dir / "page-images-receipt.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        pages = report["pages"]
    except (OSError, ValueError, KeyError, TypeError):
        raise Refused(f"{path} is absent or unreadable: run this tool first, then record final-mockups")
    found, missing = {}, []
    for slug in pages:
        record = out_dir / slug / "final-mockups" / "stage-executor-record.json"
        try:
            images = json.loads(record.read_text(encoding="utf-8")).get("images")
        except (OSError, ValueError, AttributeError):
            images = None
        if not isinstance(images, list) or not images:
            missing.append(slug)
        else:
            found[slug] = {"record": str(record), "sha256": hashlib.sha256(record.read_bytes()).hexdigest(),
                           "images": len(images)}
    if missing:
        raise Refused(f"final-mockups has no closed record with images for page(s) {missing}; nothing recorded")
    for slug, entry in found.items():
        pages[slug].setdefault("stages", {})["final-mockups"] = entry
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"recorded_final_mockups": {s: e["images"] for s, e in found.items()}}, indent=2))


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
    layouts = json.loads((scripts.parent / "references" / "page-structures.json").read_text(encoding="utf-8"))
    bands = {b["id"]: b.get("slot") or {} for b in ((layouts.get("layouts") or {}).get(role) or {}).get("sections") or []}
    draw(run, build_args, args, scripts, required_sections(slug, ledger.get("funnel_size")), bands)
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
    ap.add_argument("--ledger", type=Path, help="the run's copy_ledger.json")
    ap.add_argument("--skill71-root", type=Path)
    ap.add_argument("--brand-file", type=Path)
    ap.add_argument("--brand-owner")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--record-final-mockups", action="store_true",
                    help="no draw, no spend: merge each page's closed final-mockups record into page-images-receipt.json")
    ap.add_argument("--page", action="append", help="a matrix slug to build (repeatable)")
    ap.add_argument("--checkout-manuscript", type=Path,
                    help="the approved five-section checkout manuscript; without it checkout is reported not built")
    ap.add_argument("--decline-label", default="No thanks",
                    help="the decline button label of the downsell pages (the legacy ledger carries none)")
    ap.add_argument("--access-label", default="Access Your Purchase",
                    help="the thank-you page's access button label (the legacy ledger carries none)")
    ap.add_argument("--help-label", default="Get Support",
                    help="the thank-you page's help button label (the legacy ledger carries none)")
    ap.add_argument("--image-provider", choices=["stub", "kie"], default="kie",
                    help="kie (default) draws real wireframes and needs --allow-paid; stub writes "
                         "placeholders and needs a recorded owner approval (--stub-approved-by)")
    ap.add_argument("--stub-approved-by",
                    help="the owner approval reference that permits a STUB run; without it a stub "
                         "run is refused and, if a receipt claims one, P7-BUILD refuses to certify")
    ap.add_argument("--allow-paid", action="store_true")
    ap.add_argument("--image-model")
    ap.add_argument("--design-prose", type=Path)
    args = ap.parse_args(argv)
    try:
        if args.record_final_mockups:
            record_final_mockups(args.out_dir)
            return 0
        for flag in ("ledger", "skill71_root", "brand_file", "brand_owner"):
            if not getattr(args, flag):
                raise Refused(f"--{flag.replace('_', '-')} is required unless --record-final-mockups is given")
        if args.image_provider == "kie" and not args.allow_paid:
            raise Refused("--image-provider kie spends money; it needs --allow-paid, approved by the owner")
        if args.image_provider == "stub" and not (args.stub_approved_by or "").strip():
            # Fix plan B2: the provider must never DEFAULT to placeholder wireframes. A stub run
            # is allowed only with a recorded owner approval, written into the receipt so the
            # build gate can refuse an unapproved one.
            raise Refused("--image-provider stub writes PLACEHOLDER wireframes and needs a recorded "
                          "owner approval: pass --stub-approved-by <owner approval reference>. The "
                          "default provider is kie.")
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
        args.image_model = _image_model(args)  # once per run: every page records the same id
        report = {"funnel_size": size, "pages": {},
                  "provider": args.image_provider,
                  "stub_approval": (args.stub_approved_by or None) if args.image_provider == "stub" else None,
                  "not_built": {s: NOT_BUILT[s] for s in structure["funnel_matrix"][str(size)]
                                if s in NOT_BUILT and not (s == "checkout" and args.checkout_manuscript)}}
        for slug in slugs:
            report["pages"][slug] = run_page(slug, structure, ledger, args, scripts, entries)
        report["note"] = ("the image inventory, generation, Design Board approval and final-mockups "
                          "are client-gated stages downstream and were not run HERE. final-mockups is "
                          "NOT optional: prove_sf_build.VISUAL_STAGES requires it, so P7-BUILD refuses "
                          "to certify until the client-gated final-mockups stage has closed and "
                          "--record-final-mockups has merged its record into this receipt (fix plan B3)")
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
