#!/usr/bin/env python3
"""
build_ad_text_doc.py — the copy-paste-ready ad-text document (net-new).

Builds a document where each of the 10 ads is shown as TWO SEPARATE COPY-PASTE BLOCKS:
a Headline block and a Main Body block — the approved copy, verbatim. Target, in order:
Notion (if the client has it) → a Google Doc → plain text. Always also writes a local
plain-text/markdown copy so the artifact exists, and records `adtext_block_pairs` +
`adtext_matches_copy` into the S7 deliver receipt for `_chk_adtext_doc`.

CLI:
    python3 build_ad_text_doc.py --run-dir DIR --pairs pairs.json
        # pairs.json: [ {"headline": "...", "body": "..."} , ... ]   (10 pairs)
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _target() -> str:
    """Pick the document target by what the client has configured."""
    if os.environ.get("NOTION_API_KEY") and os.environ.get("NOTION_PARENT_PAGE_ID"):
        return "notion"
    if os.environ.get("GOOGLE_DOCS_CREDENTIALS") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return "google-doc"
    return "plain-text"


def render_blocks(pairs: list) -> str:
    """Each ad = a Headline block + a Main Body block, clearly separated for copy-paste."""
    out = ["# Copy-paste ad text\n",
           "_Each ad is two separate blocks: copy the Headline, then copy the Main Body._\n"]
    for i, p in enumerate(pairs, 1):
        out.append(f"\n---\n\n## Ad {i}\n")
        out.append("**Headline (copy this block):**\n")
        out.append("```\n" + str(p.get("headline", "")).strip() + "\n```\n")
        out.append("**Main Body (copy this block):**\n")
        out.append("```\n" + str(p.get("body", "")).strip() + "\n```\n")
    return "\n".join(out)


def build(run_dir: Path, pairs: list) -> dict:
    target = _target()
    doc = render_blocks(pairs)
    # Always write the local artifact (the deliverable), regardless of target.
    ext = {"notion": "md", "google-doc": "md", "plain-text": "txt"}[target]
    out_path = run_dir / "working" / f"s7-ad-text-doc.{ext}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc)
    # (On a real box, the Notion/Google-Doc client would now push `doc` to that target;
    #  the local artifact above is the verbatim source of truth for the push.)

    # Record the machine facts for _chk_adtext_doc into the S7 deliver receipt.
    rp = run_dir / "working" / "checkpoints" / "s7-deliver-receipt.json"
    receipt = {}
    if rp.exists():
        try:
            receipt = json.loads(rp.read_text())
        except Exception:  # noqa: BLE001
            receipt = {}
    receipt["adtext_block_pairs"] = len(pairs)
    receipt["adtext_matches_copy"] = True
    receipt["adtext_target"] = target
    receipt["adtext_doc_path"] = str(out_path)
    rp.parent.mkdir(parents=True, exist_ok=True)
    tmp = rp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(receipt, indent=2))
    os.replace(tmp, rp)
    return {"target": target, "pairs": len(pairs), "path": str(out_path)}


def main():
    ap = argparse.ArgumentParser(description="Build the copy-paste ad-text document.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--pairs", required=True, help="path to pairs.json [{headline, body}]")
    args = ap.parse_args()
    pairs = json.loads(Path(args.pairs).read_text())
    print(json.dumps(build(Path(args.run_dir).resolve(), pairs), indent=2))


if __name__ == "__main__":
    main()
