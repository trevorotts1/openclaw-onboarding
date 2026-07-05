#!/usr/bin/env python3
"""
ad_ghl_push.py — host the 10 approved images in the client's GoHighLevel library.

Makes the real calls and drops the receipt the OFFLINE check (`_chk_ghl_url`) judges:
each image gets a public, login-free GoHighLevel URL with a recorded HTTP-200. Uses the
reused `tools/ghl_media.py` (`upload_media`) + the NEW `create_media_folder()` so each
run's images land in their own named folder, with the "upload to root with a name
prefix" fallback. Uploads are namespaced by the run-id via the ledger so a retry never
re-uploads. A fabricated/placeholder link is never written — the module FAILS LOUD.

Keys: the CLIENT's own GoHighLevel LOCATION Private Integration Token (medias.write) +
location id, from the canonical env names. The operator's key NEVER appears here.

CLI:
    python3 ad_ghl_push.py --run-dir DIR
        [--images img0.png img1.png ...]   # defaults to working/s5-images/*.png
"""

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import ad_run_ledger as ledger          # noqa: E402
import ghl_media                        # noqa: E402


def _deliver_receipt_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "s7-deliver-receipt.json"


def _load_receipt(run_dir: Path) -> dict:
    p = _deliver_receipt_path(run_dir)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_receipt(run_dir: Path, obj: dict) -> None:
    p = _deliver_receipt_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, p)


def push(run_dir: Path, images: list, opener=None) -> dict:
    """Upload each image, host it, and append a delivered[] entry. Idempotent per image
    (the ledger key is the image basename) so a retry never re-uploads."""
    pit = ghl_media.resolve_location_pit()          # client's LOCATION PIT
    location_id = ghl_media.resolve_location_id()    # client's location id
    run_id = ledger.load(run_dir).get("run_id") or run_dir.name

    folder = ghl_media.create_media_folder(f"FB-AD {run_id}", location_id, pit,
                                           opener=opener)
    parent_id = folder.get("folderId")
    name_prefix = f"{run_id} — " if not parent_id else ""

    receipt = _load_receipt(run_dir)
    delivered = receipt.get("delivered", [])
    by_idx = {d.get("idx"): d for d in delivered if isinstance(d, dict)}

    for i, img in enumerate(images):
        key = f"upload:{Path(img).name}"
        if ledger.is_done(run_dir, key):
            # Already hosted under this run-id — never re-upload. But if this run's
            # receipt lost the delivered[] entry (a crash between the ledger record and
            # the receipt save, or a regenerated receipt), seed by_idx from the DURABLE
            # ledger so the rebuilt delivered[] stays complete and the fan-out / GHL-URL
            # gates still pass — recovering the stored entry instead of dropping it.
            if i not in by_idx:
                stored = ledger.result_for(run_dir, key)
                if isinstance(stored, dict) and str(stored.get("image_url", "")).strip():
                    by_idx[i] = stored
            continue
        name = f"{name_prefix}ad {i}"
        res = ghl_media.upload_media(str(img), location_id, name, pit,
                                     parent_id=parent_id, opener=opener)
        entry = {"idx": i, "image_url": res["url"], "http_status": res["http"],
                 "file_id": res["fileId"], "folder_id": parent_id}
        by_idx[i] = entry
        ledger.record(run_dir, "upload", key, 0.0, entry)

    receipt["delivered"] = [by_idx[k] for k in sorted(by_idx)]
    # Board: if no campaign_id has been stamped yet (e.g. ghl push ran before the
    # foreman filed the campaign), record the deterministic job_id (== campaign_id
    # == receipt-number) so the run groups on the board. Fail-soft: a missing
    # job-manifest or cc_board import never breaks delivery.
    if not str(receipt.get("campaign_id", "") or "").strip():
        try:
            jm_path = run_dir / "working" / "job-manifest.json"
            job_id = ""
            if jm_path.exists():
                job_id = str(json.loads(jm_path.read_text()).get("job_id", "") or "").strip()
            job_id = job_id or run_id
            if job_id:
                import cc_board  # local import keeps delivery decoupled from the board
                cc_board.stamp_campaign_id(run_dir, job_id)
                receipt = _load_receipt(run_dir)  # re-read the stamped receipt
        except Exception:  # noqa: BLE001 — board stamping must never fail delivery
            pass
    _save_receipt(run_dir, receipt)
    return receipt


def main():
    ap = argparse.ArgumentParser(description="Host the 10 images in GoHighLevel.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--images", nargs="*", default=None)
    args = ap.parse_args()
    rd = Path(args.run_dir).resolve()
    imgs = args.images
    if not imgs:
        imgs = sorted(str(p) for p in (rd / "working" / "s5-images").glob("*.png"))
    if not imgs:
        print("FATAL: no images to host (pass --images or populate working/s5-images/).",
              file=sys.stderr)
        sys.exit(2)
    receipt = push(rd, imgs)
    print(json.dumps({"hosted": len(receipt.get("delivered", []))}, indent=2))


if __name__ == "__main__":
    main()
