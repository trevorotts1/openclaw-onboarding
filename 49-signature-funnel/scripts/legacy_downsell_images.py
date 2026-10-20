#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""legacy_downsell_images.py - wireframes and mockups for the downsell pages of a 3/5/7-step funnel.

The legacy Signature Funnel (P0..P10) has no wireframe or mockup stage. A full 7-step
funnel carries TWO downsell pages (matrix slugs `downsell` and `downsell-2`); both get
desktop wireframes, mobile wireframes and the visual mockup here, by running Skill 71's
own pipeline (build_production_request.py --page-role, then stage_executor.py). Skill 71
code is reused, never copied. Launch mode has one downsell by design (LAUNCH_MODE.md);
this is the route for the second one.

  legacy_downsell_images.py --ledger <copy_ledger.json> --skill71-root <71 dir> \
      --brand-file <brand.json> --brand-owner <client> --out-dir <dir> [--page downsell-2]

Pages built: every funnel_matrix[funnel_size] slug whose page_role has an entry in
Skill 71 references/page-structures.json (today: downsell, downsell-2); --page narrows it.
A 3-step funnel has none and the run says so. Provider is the offline stub unless
--image-provider kie --allow-paid. Exit 0 ok, 2 refused or a stage failed.
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
STRUCTURE = HERE.parent / "structure" / "funnel_structure.json"
STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
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


def targets(structure, size, wanted, role_entries):
    matrix = structure["funnel_matrix"][str(size)]
    page_types = structure["page_role_map"]["page_types"]
    found = [s for s in matrix if page_types[s]["page_role"] in role_entries]
    if wanted:
        bad = [w for w in wanted if w not in found]
        if bad:
            raise Refused(f"--page {bad}: not an image-staged page of the {size}-step funnel {found}")
        return [w for w in found if w in wanted]
    return found


def run_page(slug, role, page_doc, args, scripts):
    run = args.out_dir / slug
    run.mkdir(parents=True, exist_ok=True)
    copy = run / "page-copy.json"
    copy.write_text(json.dumps(page_doc, indent=2) + "\n", encoding="utf-8")
    (run / "intake.json").write_text(json.dumps(
        {"brand_owner": args.brand_owner, "brand_file": str(args.brand_file.resolve())}), encoding="utf-8")
    model = args.image_model or ("STUB-NO-MODEL" if args.image_provider == "stub"
                                 else "gpt-image-2-5-sunburst-image-to-image")
    py = sys.executable
    for stage in STAGES:
        build = [py, str(scripts / "build_production_request.py"), "--page-role", role,
                 "--page-copy", str(copy), "--stage", stage, "--model", model,
                 "--out", f"production-request-{stage}.json", "--run-dir", "."]
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
                raise Refused(f"{slug}: {Path(cmd[1]).name} {stage} exited {proc.returncode}: " + " | ".join(tail))
    out = {}
    for stage in STAGES:
        record = run / stage / "stage-executor-record.json"
        if not record.is_file():
            raise Refused(f"{slug}: stage {stage} wrote no record at {record}")
        rec = json.loads(record.read_text(encoding="utf-8"))
        out[stage] = {"record": str(record), "sha256": hashlib.sha256(record.read_bytes()).hexdigest(),
                      "images": len(rec.get("images") or [])}
    return {"run_dir": str(run), "page_role": role, "stages": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ledger", type=Path, required=True, help="the run's copy_ledger.json")
    ap.add_argument("--skill71-root", type=Path, required=True)
    ap.add_argument("--brand-file", type=Path, required=True)
    ap.add_argument("--brand-owner", required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--page", action="append", help="a matrix slug to build (repeatable)")
    ap.add_argument("--decline-label", default="No thanks",
                    help="the decline button label (the legacy ledger carries none)")
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
        by_type = {p.get("page_type"): p for p in ledger.get("pages") or []}
        slugs = targets(structure, size, args.page, entries)
        report = {"funnel_size": size, "pages": {}}
        for slug in slugs:
            if slug not in by_type:
                raise Refused(f"{slug}: the copy ledger has no such page")
            role = structure["page_role_map"]["page_types"][slug]["page_role"]
            doc = page_object(by_type[slug], slug, args.decline_label)
            report["pages"][slug] = run_page(slug, role, doc, args, scripts)
        report["note"] = ("the image inventory, generation, Design Board approval and final-mockups "
                          "are client-gated stages downstream and were not run")
        if not slugs:
            report["note"] = f"the {size}-step funnel has no downsell page; nothing to build"
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "downsell-images-receipt.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except (Refused, OSError, ValueError, KeyError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
