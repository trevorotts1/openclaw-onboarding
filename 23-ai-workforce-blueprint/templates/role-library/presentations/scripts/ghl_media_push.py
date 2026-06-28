#!/usr/bin/env python3
"""ghl_media_push.py — host a deck's approved images + final deliverables in GHL,
AND enforce the HARD closeout gate that no deck ships without that upload.

The Media Librarian's mechanical upload half. Per the VERIFIED-WORKING Skill-48
pattern (ghl_media.create_media_folder, POST /medias/folder, Version 2021-07-28,
client LOCATION PIT), it:

  1. CREATES a named per-deck media folder ("DECK <deck-slug>") so the slide images
     are grouped under the deck, never scattered in the media root. Folder-create is
     the PRIMARY path (it returns 201 against a correctly-scoped client LOCATION PIT).
  2. If the API DECLINES folder-create (returns no folder id), falls back to (a) a
     human-supplied folder id from intake.json.ghl_media_folder_id, else (b) the
     media ROOT with a "<deck-slug> — " name PREFIX so the images stay grouped by
     name. Either way `ghl_folder_id` is recorded ("root" is a valid passing value).
  3. Uploads each approved PNG (+ the final PPTX/PDF when given) via
     ghl_media.upload_media (POST /medias/upload-file, multipart, parentId), recording
     the public storage.googleapis.com URL + fileId per file to media_library.json.

CANONICAL LEDGER PATH (the file the gates actually read):
    working/checkpoints/media_library.json
This is the SAME path SOP 9.1 (Step-0 landing zone) seeds, that delivery_gate.py and
the Delivery Concierge read, and that this module's closeout gate reads. The ledger is
MERGED (never clobbered): Step-0's folder name / version survive; the upload records
(ghl_folder_id, per-slide ghl_media_id, pptx_ghl_media_id) are added incrementally.

CLOSEOUT GATE — NO DELIVERY WITHOUT THE GHL UPLOAD (folds under AF-DELIVERY-COMPLETE):
    gate_ghl_media_complete(run_dir) -> (ok, reasons)
    `python3 ghl_media_push.py --gate --run-dir <run_dir>`   (exit 0 pass / 1 fail)
For every GHL-enabled deck it HARD-FAILS unless media_library.json records ALL THREE:
  (1) ghl_folder_id   — a real folder id OR "root" (the per-deck folder was resolved),
  (2) per-slide PNG uploads — each with a real ghl_media_id (status "complete"),
  (3) pptx_ghl_media_id — the final assembled PPTX is in the GHL media library.
The gate may be skipped by exactly ONE thing: a LOGGED owner/founder approval token in
working/checkpoints/process_manifest.json under `owner_skip_approval` (owner_approved:
true + approved_by + reason + a matching gate name). An agent setting `has_ghl:false`
on its own does NOT skip the gate — the skip must be an explicit owner decision.

FORBIDDEN: driving the GoHighLevel UI in a browser (agent-browser / Playwright /
Puppeteer / any UI automation). The media library is touched ONLY via this REST path.

Idempotent per file (the basename is the ledger key) so a retry never re-uploads.
Fail-loud: a missing LOCATION PIT raises; a non-PNG is refused; an upload returning no
fileId/url raises. No fabricated CDN URLs, ever.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghl_media  # noqa: E402  (the SHARED, verified-working module)

# The closeout code this GHL-upload gate folds under (diagnosis 4.6 / Fix-Goal 5).
GHL_UPLOAD_GATE = "AF-DELIVERY-COMPLETE"
# Owner-skip token gate names this carve-out will honor (any one matches).
_GATE_ALIASES = frozenset({
    "AF-DELIVERY-COMPLETE", "AF-BUNDLE-COMPLETE",
    "ghl_media_upload", "ghl_media", "media_library", "ghl_upload",
})
# Canonical ledger location — the file every reader/gate shares.
_LEDGER_REL = ("working", "checkpoints", "media_library.json")
_SLIDE_RE = re.compile(r"slide[\s\-_]?0*(\d{1,3})", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _ledger_path(run_dir: Path) -> Path:
    return run_dir.joinpath(*_LEDGER_REL)


def _classify(path_str: str) -> str:
    """slide PNG | pptx | pdf | image | other — drives gate-readable bucketing."""
    name = Path(path_str).name.lower()
    if name.endswith(".pptx"):
        return "pptx"
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".png") and _SLIDE_RE.search(name):
        return "slide"
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    return "other"


def _slide_number(path_str: str):
    m = _SLIDE_RE.search(Path(path_str).name)
    return int(m.group(1)) if m else None


def push_deck_media(run_dir: Path, images: list, *, deck_slug: str | None = None,
                    extra_files: list | None = None, opener=None) -> dict:
    """Create the per-deck folder and upload the approved images (+ extra files).
    Writes the gate-readable ledger to working/checkpoints/media_library.json
    (MERGED with the Step-0 seed) and returns the same dict."""
    run_dir = Path(run_dir).resolve()
    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    slug = (deck_slug or intake.get("deck_slug") or run_dir.name).strip()

    pit = ghl_media.resolve_location_pit()        # client's LOCATION PIT (never operator's)
    location_id = ghl_media.resolve_location_id()  # client's location id

    # 1) PRIMARY: create the per-deck media folder via the verified POST /medias/folder.
    folder = ghl_media.create_media_folder(f"DECK {slug}", location_id, pit, opener=opener)
    parent_id = folder.get("folderId")
    # 2) FALLBACK chain when the API declined folder-create.
    if not parent_id:
        human_folder = str(intake.get("ghl_media_folder_id") or "").strip()
        if human_folder:
            parent_id = human_folder
    name_prefix = "" if parent_id else f"{slug} — "
    ghl_folder_id = parent_id or "root"

    ledger_path = _ledger_path(run_dir)
    ledger = _read_json(ledger_path) if ledger_path.exists() else {}
    # Idempotency: keyed by absolute local path of every previously-uploaded file.
    done = {e.get("local_path"): e for e in ledger.get("uploaded", [])
            if isinstance(e, dict) and e.get("local_path")}

    uploaded = list(ledger.get("uploaded", []))
    for f in list(images) + list(extra_files or []):
        f = str(f)
        if f in done:
            continue                               # idempotent: already hosted this file
        kind = _classify(f)
        name = f"{name_prefix}{Path(f).name}"
        res = ghl_media.upload_media(f, location_id, name, pit,
                                     parent_id=parent_id, opener=opener)
        rec = {"local_path": f, "kind": kind, "name": name,
               "ghl_remote_name": name, "public_url": res["url"],
               "ghl_url": res["url"], "file_id": res["fileId"],
               "ghl_media_id": res["fileId"], "http_status": res["http"],
               "ghl_upload_status": "complete", "ghl_folder_id": ghl_folder_id,
               "uploaded_at": _now_iso()}
        sn = _slide_number(f)
        if sn is not None:
            rec["slide_number"] = sn
        uploaded.append(rec)
        done[f] = rec

    # Normalized, gate-readable projections derived from the full upload list.
    slides = sorted([e for e in uploaded if isinstance(e, dict) and e.get("kind") == "slide"],
                    key=lambda e: e.get("slide_number") or 0)
    pptx = next((e for e in uploaded if isinstance(e, dict) and e.get("kind") == "pptx"), None)

    out = {
        "deck_slug": slug,
        "ghl_folder_id": ghl_folder_id,
        "ghl_folder_name": folder.get("name") or ledger.get("ghl_folder_name") or f"DECK {slug}",
        "ghl_folder_created_via_api": bool(folder.get("folderId")),
        "uploaded": uploaded,
        "upload_count": len(uploaded),
        "slides": slides,
        "ghl_slide_upload_count": len(slides),
    }
    if pptx:
        out["pptx_ghl_media_id"] = pptx["ghl_media_id"]
        out["pptx_ghl_url"] = pptx["ghl_url"]
        out["pptx_ghl_remote_name"] = pptx["ghl_remote_name"]

    ledger.update(out)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2))
    return out


# ---------------------------------------------------------------------------
# CLOSEOUT GATE — no delivery without the GHL upload (folds under AF-DELIVERY-COMPLETE).
# ---------------------------------------------------------------------------
def _valid_owner_skip(run_dir: Path):
    """Return the owner-skip record that authorizes skipping the GHL-upload gate, or
    None. The ONLY legitimate skip: a LOGGED token in
    working/checkpoints/process_manifest.json under `owner_skip_approval` with
    owner_approved:true + a non-empty approved_by + a non-empty reason + a gate name
    that matches this gate. A list or a single dict are both accepted. An agent's own
    `has_ghl:false` is NOT a skip — only an explicit owner/founder decision is."""
    pm = _read_json(run_dir / "working" / "checkpoints" / "process_manifest.json")
    raw = pm.get("owner_skip_approval") if isinstance(pm, dict) else None
    if raw is None:
        return None
    records = raw if isinstance(raw, list) else [raw]
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if rec.get("owner_approved") is not True:
            continue
        if not str(rec.get("approved_by", "")).strip():
            continue
        if not str(rec.get("reason", "")).strip():
            continue
        gate = str(rec.get("gate") or rec.get("gate_id") or rec.get("phase_id") or "").strip()
        if gate in _GATE_ALIASES:
            return rec
    return None


def _collect_slide_uploads(media: dict) -> list:
    """Gather per-slide upload records from any of the ledger shapes (the normalized
    `slides` list, an agent-written `images` list, or `uploaded` entries that are slide
    PNGs). Deduped so the same slide is never double-counted."""
    out, seen = [], set()

    def add(entry):
        if not isinstance(entry, dict):
            return
        key = (entry.get("local_path") or entry.get("ghl_media_id")
               or entry.get("file_id") or entry.get("ghl_remote_name") or repr(entry))
        if key in seen:
            return
        seen.add(key)
        out.append(entry)

    for e in media.get("slides") or []:
        add(e)
    for e in media.get("images") or []:
        add(e)
    for e in media.get("uploaded") or []:
        if not isinstance(e, dict):
            continue
        nm = str(e.get("name") or e.get("local_path") or "")
        if e.get("kind") == "slide" or (nm.lower().endswith(".png") and _SLIDE_RE.search(nm)):
            add(e)
    return out


def _slide_complete(e: dict) -> bool:
    mid = e.get("ghl_media_id") or e.get("file_id")
    if str(e.get("ghl_upload_status", "")).lower() in ("failed", "pending"):
        return False
    return bool(str(mid or "").strip())


def gate_ghl_media_complete(run_dir, *, expected_slide_count: int | None = None):
    """HARD closeout gate. Returns (ok: bool, reasons: list[str]).

    PASS only when working/checkpoints/media_library.json records all three GHL
    uploads — folder + per-slide PNGs + final PPTX — OR a logged owner_skip_approval
    authorizes the skip. There is NO defer-to-pass: this gate runs at closeout, where a
    GHL-enabled deck with no upload record is exactly the failure it exists to catch."""
    run_dir = Path(run_dir)

    # The ONLY skip path: an explicit, logged owner/founder approval token.
    if _valid_owner_skip(run_dir) is not None:
        return True, []

    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    media = _read_json(_ledger_path(run_dir))

    # has_ghl:false WITHOUT an owner token is an agent choice, not an authorization.
    if intake.get("has_ghl") is False:
        return False, [
            f"{GHL_UPLOAD_GATE}: intake has_ghl:false but no logged owner_skip_approval in "
            "working/checkpoints/process_manifest.json. The GHL media-upload gate may be "
            "skipped ONLY by an explicit owner/founder token (owner_approved:true + "
            "approved_by + reason + gate). An agent cannot opt out of the upload on its own."]

    if not media:
        return False, [
            f"{GHL_UPLOAD_GATE}: working/checkpoints/media_library.json is missing/empty — "
            "no GHL upload record at all (folder + per-slide PNGs + final PPTX). No deck "
            "ships without the GHL media upload."]

    reasons = []

    # (1) per-deck folder resolved (a real id OR the 'root' fallback; null seed fails).
    folder = str(media.get("ghl_folder_id") or "").strip()
    if not folder:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: ghl_folder_id is null/empty — the per-deck GHL media "
            "folder was never resolved (create_media_folder, or the 'root' fallback).")

    # (2) per-slide PNG uploads, each with a real ghl_media_id.
    slides = _collect_slide_uploads(media)
    if not slides:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: no per-slide PNG upload recorded in media_library.json — "
            "every passed slide must be uploaded with a real ghl_media_id.")
    else:
        incomplete = [s for s in slides if not _slide_complete(s)]
        if incomplete:
            ids = [str(s.get("slide_number") or s.get("ghl_remote_name") or s.get("local_path"))
                   for s in incomplete]
            reasons.append(
                f"{GHL_UPLOAD_GATE}: {len(incomplete)} slide upload(s) are not complete "
                f"(no ghl_media_id or status failed/pending): {', '.join(ids)}.")
        # coverage cross-check against any recorded expected count.
        exp = expected_slide_count
        if exp is None:
            for k in ("expected_slide_count", "slide_count_final", "slide_count", "local_count"):
                v = media.get(k)
                if isinstance(v, int) and v > 0:
                    exp = v
                    break
        if isinstance(exp, int) and exp > 0 and len(slides) < exp:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: only {len(slides)} of {exp} slide PNGs are uploaded to "
                "GHL — every slide must be hosted before delivery.")

    # (3) final assembled PPTX uploaded.
    if not str(media.get("pptx_ghl_media_id") or "").strip():
        reasons.append(
            f"{GHL_UPLOAD_GATE}: pptx_ghl_media_id is absent — the final assembled PPTX was "
            "never uploaded to the GHL media library.")

    return (len(reasons) == 0), reasons


def main():
    ap = argparse.ArgumentParser(description="Host a deck's images + deliverables in GHL, "
                                             "or run the GHL-upload closeout gate.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--deck-slug", default=None)
    ap.add_argument("--images", nargs="*", default=None)
    ap.add_argument("--extra", nargs="*", default=None,
                    help="extra deliverables to upload (final PPTX/PDF).")
    ap.add_argument("--gate", action="store_true",
                    help="run the HARD closeout gate (no upload, exit 1 on fail).")
    ap.add_argument("--expected-slides", type=int, default=None,
                    help="optional per-slide coverage count for the gate.")
    args = ap.parse_args()
    rd = Path(args.run_dir).resolve()

    if args.gate:
        ok, reasons = gate_ghl_media_complete(rd, expected_slide_count=args.expected_slides)
        if ok:
            print("GHL MEDIA GATE: PASS (folder + per-slide PNGs + final PPTX recorded, "
                  "or logged owner skip)")
            return 0
        print(f"GHL MEDIA GATE: FAIL ({GHL_UPLOAD_GATE})")
        for r in reasons:
            print("  -", r)
        return 1

    imgs = args.images
    if not imgs:
        imgs = sorted(str(p) for p in (rd / "renders").glob("slide-*.png"))
    if not imgs:
        print("FATAL: no images to host (pass --images or populate renders/).",
              file=sys.stderr)
        return 2
    res = push_deck_media(rd, imgs, deck_slug=args.deck_slug, extra_files=args.extra)
    print(json.dumps(res, indent=2))
    return 0


# ---------------------------------------------------------------------------
# SELF-TEST for the closeout gate — no network, stdlib only.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails = []

    def _setup(base, *, intake=None, media=None, pm=None):
        ck = base / "working" / "checkpoints"
        ck.mkdir(parents=True, exist_ok=True)
        (base / "working" / "copy").mkdir(parents=True, exist_ok=True)
        if intake is not None:
            (base / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
        if media is not None:
            (ck / "media_library.json").write_text(json.dumps(media))
        if pm is not None:
            (ck / "process_manifest.json").write_text(json.dumps(pm))

    GOOD_MEDIA = {
        "ghl_folder_id": "fld_123",
        "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
                   {"slide_number": 2, "ghl_media_id": "m2", "ghl_upload_status": "complete"}],
        "pptx_ghl_media_id": "pptx_9",
    }

    # A — all three uploads present -> PASS.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, intake={"has_ghl": True}, media=GOOD_MEDIA)
        ok, r = gate_ghl_media_complete(base)
        if not ok:
            fails.append(f"A complete: expected PASS, got {r}")

    # B — empty ledger -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, intake={"has_ghl": True}, media={})
        ok, r = gate_ghl_media_complete(base)
        if ok or not r:
            fails.append(f"B empty: expected FAIL, got ok={ok} {r}")

    # C — folder + slides but NO pptx -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = dict(GOOD_MEDIA); m.pop("pptx_ghl_media_id")
        _setup(base, intake={"has_ghl": True}, media=m)
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("pptx_ghl_media_id" in x for x in r):
            fails.append(f"C no-pptx: expected pptx FAIL, got ok={ok} {r}")

    # D — folder + pptx but NO slide uploads -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, intake={"has_ghl": True},
               media={"ghl_folder_id": "root", "pptx_ghl_media_id": "p1"})
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("per-slide" in x for x in r):
            fails.append(f"D no-slides: expected slide FAIL, got ok={ok} {r}")

    # E — null ghl_folder_id (Step-0 seed only) -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = dict(GOOD_MEDIA); m["ghl_folder_id"] = None
        _setup(base, intake={"has_ghl": True}, media=m)
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("ghl_folder_id" in x for x in r):
            fails.append(f"E null-folder: expected folder FAIL, got ok={ok} {r}")

    # F — has_ghl:false with NO owner token -> FAIL (agent cannot opt out).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, intake={"has_ghl": False}, media={})
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("owner_skip_approval" in x for x in r):
            fails.append(f"F agent-skip: expected owner-token FAIL, got ok={ok} {r}")

    # G — has_ghl:false WITH a valid logged owner skip -> PASS (carve-out).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, intake={"has_ghl": False}, media={},
               pm={"owner_skip_approval": {"owner_approved": True, "approved_by": "owner",
                                           "reason": "client has no GHL account",
                                           "gate": "AF-DELIVERY-COMPLETE"}})
        ok, r = gate_ghl_media_complete(base)
        if not ok:
            fails.append(f"G owner-skip: expected PASS, got {r}")

    # H — owner skip present but owner_approved:false -> NOT a skip -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, intake={"has_ghl": True}, media={},
               pm={"owner_skip_approval": {"owner_approved": False, "approved_by": "x",
                                           "reason": "y", "gate": "AF-DELIVERY-COMPLETE"}})
        ok, r = gate_ghl_media_complete(base)
        if ok:
            fails.append(f"H false-token: expected FAIL, got ok={ok} {r}")

    # I — a slide upload missing its media id -> FAIL (incomplete).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = {"ghl_folder_id": "root", "pptx_ghl_media_id": "p",
             "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
                        {"slide_number": 2, "ghl_upload_status": "pending"}]}
        _setup(base, intake={"has_ghl": True}, media=m)
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("not complete" in x for x in r):
            fails.append(f"I incomplete-slide: expected FAIL, got ok={ok} {r}")

    # J — coverage shortfall (2 uploaded, 50 expected) -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = dict(GOOD_MEDIA); m["expected_slide_count"] = 50
        _setup(base, intake={"has_ghl": True}, media=m)
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("of 50" in x for x in r):
            fails.append(f"J coverage: expected coverage FAIL, got ok={ok} {r}")

    if fails:
        print("ghl_media_push gate selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("ghl_media_push gate selftest -> PASS (10 cases: complete/empty/no-pptx/"
          "no-slides/null-folder/agent-skip/owner-skip/false-token/incomplete/coverage)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
