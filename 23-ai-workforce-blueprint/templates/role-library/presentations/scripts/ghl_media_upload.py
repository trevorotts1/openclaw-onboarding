#!/usr/bin/env python3
"""ghl_media_upload.py — FIX 111: the standard over-cap rule for the deck's GHL upload.

WHY THIS EXISTS
---------------
GHL caps regular media uploads at 25 MB (HTTP 413). A 20-slide deck PPTX (~52 MB)
CANNOT be hosted as pptx. Before FIX 111 the fallback was improvised per-incident
(Defect #9 hacks): nothing enforced a standard rule at the point of upload, and the
receipt did not SAY why the pptx id was null — so a gate or a human could not tell
"the pptx was over the cap, the PDF twin is the hosted deck" from "the pptx upload
was lost".

THE STANDARD RULE (this module, one implementation, every caller):
  * A file OVER the 25 MB regular-tier cap uploads as its PDF TWIN — the deck PDF
    ({deck_slug}-FINAL.pdf) is the hosted deck deliverable.
  * The receipt (the media_library.json upload record + projections) records
    {pptx_local_path, pdf_media_id, pptx_media_id: null, reason: "over_cap"}
    so every downstream reader can SEE the deck is intentionally hosted as PDF.
  * An optional IMAGE-COMPRESSION LADDER runs before giving up on the pptx: each
    ladder step re-renders the slide PNGs smaller and re-assembles, shrinking the
    pptx toward the cap. If a step gets the pptx under the cap, the pptx uploads
    as pptx (no over_cap receipt, no PDF-twin fallback). The ladder is OFF by
    default (deck re-assembly is expensive) — callers opt in with run_ladder=True.
  * The bundle/closeout gates accept EITHER id: a real pptx media id, OR a PDF
    media id recorded with reason "over_cap". This module exposes
    hosted_deck_media_id() — the ONE accept-either-id reader every gate calls —
    plus receipt_ok(), the receipt validator the gates share.

CONTRACT
--------
Only these functions are load-bearing; everything is stdlib-only and network-free:
    GHL_MEDIA_MAX_BYTES       — 25 MB regular-tier cap (26,214,400).
    is_over_cap(path)         — True iff path exists and exceeds the cap.
    pdf_twin_for(pptx_path)   — the deck PDF twin path ({stem}.pdf sibling).
    build_receipt(...)        — the over-cap receipt dict for a PDF-twin upload.
    hosted_deck_media_id(media) -> str|None  — EITHER id, None if neither.
    hosted_deck_kind(media)   — "pptx" | "pdf" | None.
    receipt_ok(receipt)       — receipt names a real over-cap hosting.
    record_upload_receipt(ledger, rec) — merge a receipt into the upload ledger.

NO BROWSER, EVER — the media library is touched ONLY via the REST path
(ghl_media.upload_media). This module NEVER performs an upload itself; it is the
rule + receipt + gate-reader layer the transports call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# THE CAP — GHL regular media tier (Version 2021-07-28) rejects uploads over
# 25 MB with HTTP 413 (Defect #9, R14 §5.10). Same number the v3 video tier
# docs cite as the regular ceiling; one constant, one source.
# ---------------------------------------------------------------------------
GHL_MEDIA_MAX_BYTES = 25 * 1024 * 1024  # 25 MB — the regular-tier upload cap

# The receipt reason a PDF-twin upload MUST carry. Gates match this literal.
REASON_OVER_CAP = "over_cap"

_DECK_PPTX_SUFFIX = "-final.pptx"
_DECK_PDF_SUFFIX = "-final.pdf"
_SLIDE_RE_RAW = r"slide[\s\-_]?0*(\d{1,3})"


def is_over_cap(path) -> bool:
    """True iff `path` exists as a regular file and exceeds GHL_MEDIA_MAX_BYTES.
    A missing file is NOT over the cap (the upload will fail on its own; do not
    route a missing file to the PDF twin)."""
    try:
        p = Path(str(path))
        if not p.is_file():
            return False
        return os.path.getsize(str(p)) > GHL_MEDIA_MAX_BYTES
    except OSError:
        return False


def pdf_twin_for(pptx_path):
    """The deck PDF twin path for a deck pptx: same stem, .pdf suffix, same dir.
    ({deck_slug}-FINAL.pptx -> {deck_slug}-FINAL.pdf). Returns a Path; existence
    is the CALLER's check (the twin is produced by P8.1-PDF-EXPORT and may not
    exist yet for a deck that never exported)."""
    p = Path(str(pptx_path))
    return p.with_suffix(".pdf")


def build_receipt(pptx_path, pdf_upload_record):
    """Build the standard over-cap receipt for a deck hosted via its PDF twin.

    pptx_path          — the LOCAL pptx that exceeded the cap (never uploaded).
    pdf_upload_record  — the upload record the PDF twin's POST produced: a dict
                         carrying at least {"ghl_media_id"/"file_id", "ghl_url",
                         "ghl_remote_name"} in the media_library.json record shape.

    Returns the receipt dict:
        {pptx_local_path, pdf_media_id, pptx_media_id: None, reason: "over_cap",
         pdf_url, pdf_remote_name, cap_bytes, pptx_bytes}
    Raises ValueError on a falsy pptx path or a record with no media id — a
    receipt without the PDF's real id is exactly the phantom this module exists
    to prevent."""
    pptx_local = str(pptx_path or "").strip()
    if not pptx_local:
        raise ValueError("build_receipt: pptx_path is required — the receipt must "
                         "name the local pptx that exceeded the cap")
    if not isinstance(pdf_upload_record, dict):
        raise ValueError("build_receipt: pdf_upload_record must be the PDF twin's "
                         "upload record dict")
    pdf_id = str(pdf_upload_record.get("ghl_media_id")
                 or pdf_upload_record.get("file_id") or "").strip()
    if not pdf_id:
        raise ValueError("build_receipt: pdf_upload_record carries no ghl_media_id — "
                         "a receipt must name the REAL media id of the uploaded PDF "
                         "twin (no fabricated ids)")
    try:
        pptx_bytes = os.path.getsize(pptx_local)
    except OSError:
        pptx_bytes = None
    return {
        "pptx_local_path": pptx_local,
        "pdf_media_id": pdf_id,
        "pptx_media_id": None,
        "reason": REASON_OVER_CAP,
        "pdf_url": str(pdf_upload_record.get("ghl_url")
                       or pdf_upload_record.get("public_url") or ""),
        "pdf_remote_name": str(pdf_upload_record.get("ghl_remote_name")
                               or pdf_upload_record.get("name") or ""),
        "cap_bytes": GHL_MEDIA_MAX_BYTES,
        "pptx_bytes": pptx_bytes,
    }


def receipt_ok(receipt) -> bool:
    """Validate a receipt the gates trust. True iff it is a dict that names a real
    over-cap hosting: pptx_media_id is None, reason == "over_cap", and
    pdf_media_id is a non-empty id. Anything else is not a receipt the
    accept-either-id gates may honor."""
    if not isinstance(receipt, dict):
        return False
    if receipt.get("pptx_media_id") is not None:
        return False
    if str(receipt.get("reason") or "") != REASON_OVER_CAP:
        return False
    return bool(str(receipt.get("pdf_media_id") or "").strip())


def hosted_deck_media_id(media) -> str | None:
    """THE accept-either-id reader. Given the parsed media_library.json (dict),
    return the hosted deck's real media id:
      * a real pptx media id (the canonical path) — preferred; OR
      * the PDF twin's media id, ONLY when the ledger carries a VALID over-cap
        receipt (reason "over_cap", pptx_media_id null, pdf id present).
    Returns None when neither exists — the caller gates on that, unchanged.
    Never raises: a malformed ledger is a None, never a crash."""
    if not isinstance(media, dict):
        return None
    pptx_id = str(media.get("pptx_ghl_media_id") or "").strip()
    if pptx_id:
        return pptx_id
    rec = media.get("deck_upload_receipt")
    if receipt_ok(rec):
        return str(rec["pdf_media_id"]).strip()
    # Legacy shape (Defect #9 interim): deck_upload_kind == "pdf" with the PDF's
    # id recorded in pptx_ghl_media_id is ALSO an accept-either-id pass, but only
    # when the kind marker says so — a bare id with no kind marker is NOT proof.
    if str(media.get("deck_upload_kind") or "") == "pdf" and pptx_id:
        return pptx_id
    return None


def hosted_deck_kind(media) -> str | None:
    """Which artifact is the hosted deck: "pptx" (canonical), "pdf" (over-cap
    twin), or None (nothing hosted). Same precedence as hosted_deck_media_id."""
    if not isinstance(media, dict):
        return None
    if str(media.get("pptx_ghl_media_id") or "").strip():
        rec = media.get("deck_upload_receipt")
        if receipt_ok(rec) and not str(rec.get("pptx_media_id") or "").strip():
            return "pdf"
        # Legacy Defect #9 interim shape: deck_upload_kind == "pdf" marks the id
        # as the PDF twin's id, not a real pptx upload.
        if str(media.get("deck_upload_kind") or "") == "pdf":
            return "pdf"
        return "pptx"
    rec = media.get("deck_upload_receipt")
    if receipt_ok(rec):
        return "pdf"
    if str(media.get("deck_upload_kind") or "") == "pdf":
        return "pdf"
    return None


def record_upload_receipt(ledger: dict, receipt: dict) -> dict:
    """Merge an over-cap receipt into the upload ledger (media_library.json
    shape, MUTATED in place and returned). Writes the standard projections:
      deck_upload_receipt  — the receipt itself (the reason carrier),
      deck_upload_kind     — "pdf" (hosted-as-PDF marker the legacy readers see),
      pptx_local_path      — the local pptx that exceeded the cap.
    It does NOT touch ghl_folder_id / slides / uploaded — the caller's own
    bookkeeping. Never raises on a bad receipt; it just records nothing (the
    gates will say why)."""
    if not isinstance(ledger, dict) or not receipt_ok(receipt):
        return ledger
    ledger["deck_upload_receipt"] = dict(receipt)
    ledger["deck_upload_kind"] = "pdf"
    ledger["pptx_local_path"] = str(receipt.get("pptx_local_path") or "")
    return ledger


# ---------------------------------------------------------------------------
# OPTIONAL IMAGE-COMPRESSION LADDER (FIX 111 — "before giving up on the pptx").
# Each step: re-encode the slide PNGs at a lower quality/width, re-assemble the
# pptx, re-measure. If a step lands under the cap, the pptx uploads AS PPTX.
# The ladder is stdlib+PIL; PIL absence degrades to "no ladder" (the PDF-twin
# fallback is always the final answer).
# ---------------------------------------------------------------------------
LADDER_MAX_DIMENSIONS = (3840, 2560, 1920)   # px longest-side steps
LADDER_JPEG_QUALITIES = (80, 60, 40)         # only for JPEG-backed slide images


def _slide_pngs(run_dir: Path) -> list:
    renders = run_dir / "renders"
    if not renders.is_dir():
        return []
    return sorted(renders.glob("slide-*.png"))


def _reencode_png(png: Path, out: Path, max_dim: int) -> bool:
    """Re-encode one slide PNG at <= max_dim longest side (PIL LANCZOS).
    Returns True on success; False when PIL is absent or the encode fails
    (the ladder step then aborts and the PDF twin takes over)."""
    try:
        from PIL import Image  # noqa: WPS433 — optional, degrade loudly
    except Exception:  # noqa: BLE001
        return False
    try:
        with Image.open(str(png)) as im:
            w, h = im.size
            scale = min(1.0, max_dim / float(max(w, h)))
            if scale < 1.0:
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                               Image.LANCZOS)
            out.parent.mkdir(parents=True, exist_ok=True)
            im.save(str(out), format="PNG", optimize=True)
        return out.is_file() and out.stat().st_size > 0
    except Exception:  # noqa: BLE001 — a bad PNG aborts the step, not the push
        return False


def run_compression_ladder(run_dir, pptx_path, *, assemble, max_steps=3) -> dict:
    """Run the ladder for an over-cap pptx. `assemble(pptx_dest: Path) -> bool`
    is the CALLER's re-assembly step (build_deck's assembler) — this module never
    forks the assembler; it only prepares compressed inputs and measures.

    Per step: re-encode every slide PNG in working/ladder/step-<n>/ at the step's
    longest side, ask the caller to assemble a candidate pptx, measure it. FIRST
    candidate under the cap wins; its path is returned. Returns
        {"ok": bool, "pptx": Path|None, "steps": [...]}
    where steps[i] = {max_dim, pptx_bytes, under_cap, error?}."""
    run_dir = Path(run_dir)
    pptx_path = Path(pptx_path)
    out = {"ok": False, "pptx": None, "steps": []}
    if assemble is None or not pptx_path.is_file():
        return out
    pngs = _slide_pngs(run_dir)
    if not pngs:
        out["steps"].append({"error": "no slide-*.png renders found to re-encode"})
        return out
    ladder_root = run_dir / "working" / "ladder"
    for i, max_dim in enumerate(LADDER_MAX_DIMENSIONS[:max(1, max_steps)]):
        step_dir = ladder_root / f"step-{i + 1}"
        step_ok = True
        for png in pngs:
            if not _reencode_png(png, step_dir / png.name, max_dim):
                step_ok = False
                out["steps"].append({"max_dim": max_dim,
                                     "error": f"re-encode failed: {png.name}"})
                break
        if not step_ok:
            continue
        candidate = ladder_root / f"step-{i + 1}" / pptx_path.name
        try:
            assembled = assemble(candidate)
        except Exception as exc:  # noqa: BLE001 — a failed assemble is a step loss
            out["steps"].append({"max_dim": max_dim,
                                 "error": f"assemble raised: {exc!r}"})
            continue
        if not assembled or not candidate.is_file():
            out["steps"].append({"max_dim": max_dim,
                                 "error": "assemble produced no candidate pptx"})
            continue
        size = candidate.stat().st_size
        under = size <= GHL_MEDIA_MAX_BYTES
        out["steps"].append({"max_dim": max_dim, "pptx_bytes": size,
                             "under_cap": under})
        if under:
            out["ok"] = True
            out["pptx"] = candidate
            break
    return out


__all__ = [
    "GHL_MEDIA_MAX_BYTES",
    "REASON_OVER_CAP",
    "is_over_cap",
    "pdf_twin_for",
    "build_receipt",
    "receipt_ok",
    "hosted_deck_media_id",
    "hosted_deck_kind",
    "record_upload_receipt",
    "run_compression_ladder",
]

# ---------------------------------------------------------------------------
# SELF-TEST — no network, stdlib + optional PIL. `--selftest` proves the rule.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails = []

    # A — a 52 MB pptx is over the cap; a 10 MB pptx is not.
    with tempfile.TemporaryDirectory() as t:
        big = Path(t) / "demo-deck-FINAL.pptx"
        big.write_bytes(b"PK\x03\x04" + b"\x00" * (52 * 1024 * 1024))
        small = Path(t) / "small-deck-FINAL.pptx"
        small.write_bytes(b"PK\x03\x04" + b"\x00" * (10 * 1024 * 1024))
        if not is_over_cap(str(big)):
            fails.append("A1 over-cap: 52MB pptx not detected over cap")
        if is_over_cap(str(small)):
            fails.append("A2 under-cap: 10MB pptx flagged over cap")
        if is_over_cap(str(Path(t) / "missing.pptx")):
            fails.append("A3 missing file must not be over-cap")
        # B — the PDF twin path.
        twin = pdf_twin_for(big)
        if twin.name != "demo-deck-FINAL.pdf" or twin.parent != big.parent:
            fails.append(f"B pdf-twin: wrong twin path {twin}")

    # C — receipt build + validation.
    rec = build_receipt("/tmp/x/demo-deck-FINAL.pptx",
                        {"ghl_media_id": "pdf_9", "ghl_url": "https://u", "ghl_remote_name": "n"})
    if not receipt_ok(rec):
        fails.append("C1 receipt: a well-formed receipt failed receipt_ok")
    if rec["pptx_media_id"] is not None or rec["reason"] != "over_cap":
        fails.append("C2 receipt: wrong shape")
    bad = dict(rec)
    bad["pdf_media_id"] = ""
    if receipt_ok(bad):
        fails.append("C3 receipt: empty pdf id accepted")
    bad2 = dict(rec)
    bad2["reason"] = "unknown"
    if receipt_ok(bad2):
        fails.append("C4 receipt: wrong reason accepted")
    bad3 = dict(rec)
    bad3["pptx_media_id"] = "pptx_1"
    if receipt_ok(bad3):
        fails.append("C5 receipt: non-null pptx id accepted")
    try:
        build_receipt("/tmp/x/deck-FINAL.pptx", {"ghl_media_id": ""})
        fails.append("C6 receipt: missing pdf id did not raise")
    except ValueError:
        pass

    # D — accept-either-id reader.
    media = {"ghl_folder_id": "root",
             "slides": [{"slide_number": 1, "ghl_media_id": "m1"}],
             "deck_upload_receipt": rec}
    if hosted_deck_media_id(media) != "pdf_9":
        fails.append("D1 either-id: over-cap receipt not honored")
    if hosted_deck_kind(media) != "pdf":
        fails.append("D2 either-id: kind must be pdf under a valid receipt")
    # pptx wins when a real pptx id exists with no receipt.
    m2 = {"pptx_ghl_media_id": "pptx_1"}
    if hosted_deck_media_id(m2) != "pptx_1" or hosted_deck_kind(m2) != "pptx":
        fails.append("D3 either-id: canonical pptx id not honored")
    # A real pptx id PLUS a receipt is ambiguous -> pptx (canonical wins) but the
    # receipt is then invalid (pptx id non-null gate): hosted stays pptx.
    m3 = {"pptx_ghl_media_id": "pptx_1", "deck_upload_receipt": rec}
    if hosted_deck_media_id(m3) != "pptx_1":
        fails.append("D4 either-id: pptx id must win over a receipt")
    # No receipt, no pptx id -> None (the gate fails, as before).
    if hosted_deck_media_id({"ghl_folder_id": "root"}) is not None:
        fails.append("D5 either-id: empty ledger must yield None")
    # Legacy deck_upload_kind="pdf" shape is honored.
    m4 = {"pptx_ghl_media_id": "legacy_1", "deck_upload_kind": "pdf"}
    if hosted_deck_media_id(m4) != "legacy_1" or hosted_deck_kind(m4) != "pdf":
        fails.append("D6 either-id: legacy pdf-kind shape not honored")
    # Bare id with NO kind marker and NO receipt is NOT proof.
    if hosted_deck_kind({"pptx_ghl_media_id": "x"}) != "pptx":
        fails.append("D7 either-id: bare pptx id must be kind pptx")

    # E — ledger merge.
    led = {"ghl_folder_id": "root"}
    record_upload_receipt(led, rec)
    if led.get("deck_upload_kind") != "pdf" or not receipt_ok(led.get("deck_upload_receipt")):
        fails.append("E1 merge: receipt not recorded")
    bad_led = {}
    record_upload_receipt(bad_led, {})
    if bad_led:
        fails.append("E2 merge: invalid receipt recorded nothing (expected)")

    # F — the 25MB fixture end-to-end: 52MB pptx -> twin receipt -> gate id; and the
    # ladder returns a no-photos step error cleanly (no crash on an empty run dir).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        (base / "delivery").mkdir(parents=True, exist_ok=True)
        big = base / "delivery" / "demo-deck-FINAL.pptx"
        big.write_bytes(b"PK\x03\x04" + b"\x00" * (52 * 1024 * 1024))
        ledger = {"ghl_folder_id": "root"}
        pdf_rec = build_receipt(str(big), {"ghl_media_id": "pdf_big",
                                           "ghl_url": "https://u",
                                           "ghl_remote_name": "demo-deck-FINAL.pdf"})
        record_upload_receipt(ledger, pdf_rec)
        if hosted_deck_media_id(ledger) != "pdf_big":
            fails.append("F1 fixture: 52MB deck hosted as PDF not accepted by the gate")
        lad = run_compression_ladder(base, big, assemble=lambda p: False)
        if lad["ok"] or not lad["steps"]:
            fails.append("F2 ladder: empty-run ladder must report a clean step loss")
        if any("slide-01.png" in str(s) for s in lad["steps"]):
            pass  # a run with renders would list them; empty run reports the PNG miss

    if fails:
        print("ghl_media_upload selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("ghl_media_upload selftest -> PASS (over-cap detect/pdf-twin/receipt/"
          "either-id reader/ledger merge/ladder degrade)")
    return 0


if __name__ == "__main__":
    import sys as _sys
    if "--selftest" in _sys.argv:
        _sys.exit(_selftest())
    print(__doc__)
    _sys.exit(0)
