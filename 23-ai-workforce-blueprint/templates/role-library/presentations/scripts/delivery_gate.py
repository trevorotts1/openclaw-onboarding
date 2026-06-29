#!/usr/bin/env python3
"""
delivery_gate.py — MECHANICAL last-mile delivery enforcer (R9-F9 fix).

Until now the client-facing last mile (AF-DH1 five-file whitelist, the GHL upload
record, and the SOP 9.4 ground-truth destination check) was DOCTRINE-ONLY: the codes
AF-DELIVER / AF-DH1 / AF-DELIVERY-COMPLETE are enforced_by "closeout_gate" with a
null py_symbol, and gate_integrity_check.py (Guard A) exempts non-build_deck codes.
So the only mechanical bundle gate was build_deck.py's AF-BUNDLE-COMPLETE over the
NINE-file operator build bundle in ~/Downloads — the actual client package
(delivery/[DECK_SLUG]-FINAL/, the FIVE whitelisted files) had no coded enforcer and
relied on the Concierge agent obeying the SOPs. This script closes that gap.

It mechanically enforces, over a run dir:
  1. AF-DH1 — delivery/[DECK_SLUG]-FINAL/ contains EXACTLY the five whitelisted,
     correctly-named client files and NOTHING else (no extras, no working/ dirs,
     no .md guide/speech, pptx/pdf carry the -FINAL suffix).
  2. GHL upload record — when the resolved delivery_plan.json carries a `ghl`
     destination, working/checkpoints/media_library.json must carry a non-null
     `pptx_ghl_media_id` (the upload actually happened, not just planned).
  3. SOP 9.4 ground-truth — every destination in delivery_plan.json is verified:
     a `mac_downloads` destination's `verify_anchor` file exists on disk; a `ghl`
     destination has its upload id; a `drive` destination has its file ids.

The in-pipeline run-dir helper delivery_gate(run_dir) DEFERS (pass, "not at delivery
stage") when neither the delivery package dir nor a delivery_plan.json exists — a
pre-delivery render must not be blocked. A delivery that was ATTEMPTED (plan present)
but is missing/partial FAILS.

================================================================================
OUT-OF-BAND DELIVERY BOUNDARY GATE (the #1 fix — fail-closed artifact inspection).
================================================================================
Every other enforcement gate lives INSIDE the pipeline, so an agent whose routing
fails can HAND-BUILD a deck (python-pptx / Pillow / Google-Slides, native overlaid
text, no kie.ai images) and SHIP it, bypassing everything. gate_delivered_artifact()
closes that hole by inspecting the SHIPPED ARTIFACT itself — regardless of how it was
produced — and is FAIL-CLOSED:

  (1) ARTIFACT PROVENANCE — open the delivered .pptx/.pdf. A canonical deck is
      full-bleed kie.ai images with the words BAKED IN, so it has NO selectable body
      text. Any SELECTABLE native on-slide text (a <a:t> run in a real slide part, or
      embedded fonts + text operators in the PDF) means the deck was hand-built /
      overlaid -> REJECT (AF-OVERLAY-DELIVERED). An unreadable artifact cannot be
      proven kie-baked -> REJECT (AF-NOT-KIE-RENDERED).
  (2) KIE PROVENANCE — require a real kie.ai taskId per slide in the process
      manifest's render record; no taskIds -> the images were not kie-rendered ->
      REJECT (AF-NOT-KIE-RENDERED).
  (3) NO-RUN-DIR FAIL-CLOSED — a deck with no governed run dir
      (working/checkpoints/process_manifest.json) was hand-built OUTSIDE
      run_signature_deck.py -> REJECT (AF-NO-RUN-DIR). (The legacy run-dir helper
      delivery_gate() still defers pre-delivery; the BOUNDARY gate never does.)
  (4) BUNDLE-COMPLETENESS — require the full deliverable set (deck + presenter speech
      + audio + presenter guide + teleprompter + GoHighLevel upload record) before
      delivery; missing siblings -> REJECT (AF-BUNDLE-COMPLETE). This is why a partial
      "1 of 12" delivery is impossible.

The ONLY bypass is an explicit, LOGGED owner_skip_approval token (reuse of the audited
canonical_render_guard token: owner_approved:true + approved_by + reason + gate=<AF
code>) recorded in process_manifest.json or, for an out-of-pipeline artifact, an
owner_skip_approval.json adjacent to the artifact. No agent may self-approve.

ZERO third-party deps (stdlib json / re / os / sys / zipfile / zlib / pathlib /
argparse / tempfile only) so it runs identically in the repo and on a deployed client
box — it does NOT rely on python-pptx being installed.

PUBLIC API (imported by test_preflight.py + run_signature_deck.py):
    delivery_gate(run_dir: Path) -> tuple[bool, list[str]]
        in-pipeline run-dir helper (AF-DH1 / upload-record / destination). Defers
        pre-delivery.
    gate_delivered_artifact(artifact_path, run_dir=None) -> tuple[bool, list[str]]
        the FAIL-CLOSED delivery boundary gate over the SHIPPED ARTIFACT.
    inspect_pptx_artifact(pptx_path) -> list[tuple[str, str]]
    inspect_pdf_artifact(pdf_path) -> list[tuple[str, str]]
    check_kie_provenance(run_dir) -> str
    check_af_dh1(package_dir: Path) -> str   # "" on pass, reason on fail
    find_client_package(run_dir: Path) -> Path | None

EXIT CODES (CLI):
    0 — delivery complete (or deferred: pre-delivery), gate clean.
    1 — one or more last-mile / boundary failures.
    2 — could not run (bad args / unreadable run dir).

USAGE:
    python3 delivery_gate.py <run_dir>
    python3 delivery_gate.py --artifact <deck.pptx> [--run-dir <dir>]
    python3 delivery_gate.py --selftest      # built-in pass + fail fixtures
"""

import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

# The FIVE client-package files (AF-DH1 whitelist), kept in lockstep with
# sops/delivery-concierge-sops.md SOP 9.0 step 3a and PIPELINE-MANIFEST.json
# client_package_files. PRESENTERS-SPEECH is PLURAL (the canonical producer name).
EXACT_NAME_WHITELIST = frozenset({
    "PRESENTER-GUIDE.pdf",
    "PRESENTERS-SPEECH.pdf",
    "PRESENTER-AUDIO.mp3",
})
# Blocklist substrings/suffixes (belt-and-suspenders mirror of SOP 9.0 step 3b).
BLOCKLIST_SUFFIXES = (
    ".py", ".log", ".txt", "_manifest.json", "_qc_log.json", "_run.log",
    "QC-FINAL.md",
)
FORBIDDEN_SUBDIRS = frozenset({
    "working", "prompts", "images", "renders", "qc", "scripts", "checkpoints",
})

# ---------------------------------------------------------------------------
# Boundary-gate auto-fail codes — EXACT strings. AF-NO-RUN-DIR + AF-NOT-KIE-RENDERED
# are NEW codes registered in PIPELINE-MANIFEST.autofails (check_script -> this file)
# and the MASTER ruleset Section 5. AF-OVERLAY-DELIVERED + AF-BUNDLE-COMPLETE are
# REUSED (already registered) at the delivery boundary.
# ---------------------------------------------------------------------------
AF_NO_RUN_DIR = "AF-NO-RUN-DIR"
AF_NOT_KIE_RENDERED = "AF-NOT-KIE-RENDERED"
AF_OVERLAY_DELIVERED = "AF-OVERLAY-DELIVERED"
AF_BUNDLE_COMPLETE = "AF-BUNDLE-COMPLETE"

# sync_check.py LOCKSTEP — HOLE B / C1 emission registry. sync_check scans every
# script named in an autofails[].check_script for `"code": "AF-..."` emission dicts
# and FAILS (exit 4) if any emitted code is not registered in the manifest. This
# block makes the EXACT set of codes this gate can emit machine-discoverable. Every
# entry below MUST stay registered in PIPELINE-MANIFEST.autofails. Do NOT add a
# `"code": "AF-..."` literal anywhere else in this file for an unregistered code.
_EMITTED_AF_CODES = (
    {"code": "AF-NO-RUN-DIR"},        # no governed run dir -> hand-built outside pipeline
    {"code": "AF-NOT-KIE-RENDERED"},  # no kie.ai taskId per slide / unreadable artifact
    {"code": "AF-OVERLAY-DELIVERED"}, # selectable native on-slide text (overlay, not baked)
    {"code": "AF-BUNDLE-COMPLETE"},   # deliverable set incomplete (missing siblings)
)

# A taskId that is not a real kie.ai bake (mirrors build_deck.py's I14 gate).
_BAD_TASK_IDS = frozenset({None, "", "native", "placeholder", "none", "null", "n/a"})


def _categorize(name: str) -> str:
    """Return the client-package category for a filename, or '' if not whitelisted."""
    if name == "PRESENTER-GUIDE.pdf":
        return "guide_pdf"
    if name == "PRESENTERS-SPEECH.pdf":
        return "speech_pdf"
    if name == "PRESENTER-AUDIO.mp3":
        return "audio_mp3"
    if name.endswith("-FINAL.pptx"):
        return "deck_pptx"
    if name.endswith("-FINAL.pdf"):
        return "deck_pdf"
    return ""


def check_af_dh1(package_dir: Path) -> str:
    """AF-DH1 hygiene gate over the resolved client package dir. Returns '' on PASS,
    or a specific failure reason. Enforces: exactly the five whitelisted client files,
    correctly named; no extra/wrongly-named file; no forbidden subdir; pptx/pdf carry
    the -FINAL suffix; no .md guide/speech."""
    if not package_dir.is_dir():
        return f"AF-DH1: client package dir {package_dir} does not exist"
    found = {}
    for child in sorted(package_dir.iterdir()):
        nm = child.name
        if child.is_dir():
            if nm in FORBIDDEN_SUBDIRS:
                return f"AF-DH1: forbidden dev directory in client package: {nm}/"
            return f"AF-DH1: unexpected subdirectory in client package: {nm}/"
        # Format check: a .md guide/speech is an explicit fail (must be .pdf).
        low = nm.lower()
        if low.endswith(".md") and ("presenter-guide" in low or "presenters-speech" in low
                                    or "presenter-speech" in low):
            return f"AF-DH1: guide/speech present as .md (must be .pdf): {nm}"
        for bad in BLOCKLIST_SUFFIXES:
            if nm.endswith(bad):
                return f"AF-DH1: blocklisted dev artifact in client package: {nm}"
        cat = _categorize(nm)
        if not cat:
            return f"AF-DH1: file not on the five-item whitelist: {nm}"
        if cat in found:
            return (f"AF-DH1: two files map to the same client slot {cat!r}: "
                    f"{found[cat]} + {nm}")
        found[cat] = nm
    required = {"deck_pptx", "deck_pdf", "guide_pdf", "speech_pdf", "audio_mp3"}
    missing = required - set(found)
    if missing:
        return (f"AF-DH1: client package is incomplete — missing "
                f"{', '.join(sorted(missing))} (have: {', '.join(sorted(found.values())) or 'nothing'})")
    return ""


def find_client_package(run_dir: Path):
    """Locate the single delivery/[DECK_SLUG]-FINAL/ client package dir, or None."""
    delivery = run_dir / "delivery"
    if not delivery.is_dir():
        return None
    candidates = [p for p in delivery.iterdir() if p.is_dir() and p.name.endswith("-FINAL")]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    # Ambiguous: more than one -FINAL package. Caller treats None-with-many as a fail.
    return candidates  # type: ignore[return-value]


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def _check_destinations(run_dir: Path, plan: dict) -> list:
    """SOP 9.4 ground-truth: every resolved destination must be verifiable."""
    reasons = []
    dests = plan.get("destinations") or []
    if not isinstance(dests, list) or not dests:
        reasons.append("SOP-9.4: delivery_plan.json has no resolved destinations")
        return reasons
    media = _load_json(run_dir / "working" / "checkpoints" / "media_library.json") or {}
    for d in dests:
        if not isinstance(d, dict):
            reasons.append(f"SOP-9.4: malformed destination entry: {d!r}")
            continue
        dtype = d.get("type")
        if dtype == "mac_downloads":
            anchor = d.get("verify_anchor") or ""
            ap = Path(anchor.replace("~", str(Path.home()), 1)) if anchor.startswith("~") else Path(anchor)
            if not anchor:
                reasons.append("SOP-9.4: mac_downloads destination has no verify_anchor")
            elif not ap.is_file():
                reasons.append(f"SOP-9.4: mac_downloads verify_anchor missing on disk: {anchor}")
        elif dtype == "ghl":
            if not media.get("pptx_ghl_media_id"):
                reasons.append("AF-DELIVER/GHL: ghl destination resolved but "
                               "media_library.json has no pptx_ghl_media_id (upload record absent)")
        elif dtype == "drive":
            ids = plan.get("drive_file_ids") or media.get("drive_file_ids")
            if not ids:
                reasons.append("SOP-9.4: drive destination resolved but no drive_file_ids recorded")
        else:
            reasons.append(f"SOP-9.4: unknown/unimplemented destination type: {dtype!r}")
    return reasons


# ===========================================================================
# OUT-OF-BAND DELIVERY BOUNDARY GATE — inspects the SHIPPED ARTIFACT, fail-closed.
# ===========================================================================
# (1) ARTIFACT PROVENANCE — selectable-text detection (stdlib only, no python-pptx).
# ---------------------------------------------------------------------------
_AT_RE = re.compile(r"<a:t>(.*?)</a:t>", re.S)          # PPTX on-slide text runs
_TAG_RE = re.compile(r"<[^>]+>")


def inspect_pptx_artifact(pptx_path):
    """Open the delivered .pptx as the OOXML zip it MUST be and inspect every real
    ppt/slides/slideN.xml part for SELECTABLE native on-slide text (<a:t> runs). A
    canonical deck is full-bleed kie.ai gpt-image-2 images with the words BAKED IN —
    so a real slide part has NO non-empty <a:t> run (speaker notes live in a separate
    ppt/notesSlides part and are allowed). Any selectable on-slide text means the deck
    was hand-built / overlaid (python-pptx add_textbox, Google Slides / Keynote
    export), not kie-rendered.

    Returns a list of (af_code, reason). Stdlib zipfile + re only — runs on any box
    with no python-pptx dependency. Fail-closed: an artifact that cannot be opened as
    an OOXML package is REJECTED (it cannot be proven kie-baked)."""
    findings = []
    try:
        zf = zipfile.ZipFile(str(pptx_path))
    except Exception:  # noqa: BLE001
        return [(AF_NOT_KIE_RENDERED,
                 f"AF-NOT-KIE-RENDERED: delivered .pptx {pptx_path.name} is not a readable "
                 "OOXML package — it cannot be proven to be a kie-baked image-only deck "
                 "(fail-closed; a hand-built decoy is rejected).")]
    try:
        names = zf.namelist()
        slide_xmls = [n for n in names
                      if n.startswith("ppt/slides/slide") and n.endswith(".xml")
                      and "/_rels/" not in n]
        if not slide_xmls:
            findings.append((AF_NOT_KIE_RENDERED,
                f"AF-NOT-KIE-RENDERED: {pptx_path.name} has no ppt/slides/slideN.xml parts "
                "— not a real rendered deck (fail-closed)."))
            return findings
        offenders = []
        for n in sorted(slide_xmls):
            try:
                xml = zf.read(n).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                continue
            for raw in _AT_RE.findall(xml):
                txt = _TAG_RE.sub("", raw).strip()
                if txt:
                    offenders.append(f"{n.split('/')[-1]}:{txt[:48]!r}")
        if offenders:
            findings.append((AF_OVERLAY_DELIVERED,
                f"AF-OVERLAY-DELIVERED: {pptx_path.name} carries SELECTABLE native on-slide "
                "text (<a:t> runs) instead of words baked into a kie.ai image — "
                + "; ".join(offenders[:8])
                + ". A canonical deck is full-bleed gpt-image-2 images with NO selectable "
                "body text; this deck was HAND-BUILT (python-pptx / Google Slides / overlay), "
                "not kie-rendered. REJECTED."))
    finally:
        zf.close()
    return findings


# PDF provenance — embedded fonts + text-showing operators both present = selectable
# text. A canonical image-only PDF (exported from an image-only deck) has neither.
_PDF_FONT_RE = re.compile(rb"/(?:BaseFont|FontFile\d?)\b|/Type\s*/Font\b")
_PDF_BT_RE = re.compile(rb"\bBT\b")
_PDF_TJ_RE = re.compile(rb"(?:Tj|TJ)\b")
_PDF_STREAM_RE = re.compile(rb"stream\r?\n(.*?)endstream", re.S)


def _pdf_text_blobs(raw):
    """Yield the raw bytes plus every flate-inflated content stream, so text operators
    are visible whether or not the producer compressed the page content."""
    yield raw
    for m in _PDF_STREAM_RE.finditer(raw):
        blob = m.group(1)
        for attempt in (blob, blob.strip(b"\r\n")):
            try:
                yield zlib.decompress(attempt)
                break
            except Exception:  # noqa: BLE001
                continue


def inspect_pdf_artifact(pdf_path):
    """Best-effort, stdlib-only provenance read of a delivered .pdf. A canonical deck
    PDF is exported from an image-only .pptx: image XObjects, NO embedded fonts, NO
    text-showing operators. We REJECT only on STRONG evidence of real selectable text —
    BOTH an embedded font resource (/BaseFont | /FontFile | /Type /Font) AND BT...Tj/TJ
    text operators — so a genuinely image-only PDF is never false-failed. Returns a
    list of (af_code, reason)."""
    findings = []
    try:
        raw = pdf_path.read_bytes()
    except Exception:  # noqa: BLE001
        return [(AF_NOT_KIE_RENDERED,
                 f"AF-NOT-KIE-RENDERED: {pdf_path.name} is unreadable — cannot prove it is "
                 "an image-only kie-baked deck (fail-closed).")]
    if not raw.startswith(b"%PDF"):
        return [(AF_NOT_KIE_RENDERED,
                 f"AF-NOT-KIE-RENDERED: {pdf_path.name} is not a PDF (no %PDF header) — "
                 "fail-closed.")]
    has_font = bool(_PDF_FONT_RE.search(raw))
    has_text_ops = any(_PDF_BT_RE.search(b) and _PDF_TJ_RE.search(b)
                       for b in _pdf_text_blobs(raw))
    if has_font and has_text_ops:
        findings.append((AF_OVERLAY_DELIVERED,
            f"AF-OVERLAY-DELIVERED: {pdf_path.name} carries SELECTABLE text (embedded font "
            "resource + BT...Tj/TJ text-showing operators) instead of words baked into "
            "kie.ai images. A canonical deck PDF is image-only — no fonts, no text "
            "operators. This PDF was HAND-BUILT / overlaid, not exported from a kie-rendered "
            "image-only deck. REJECTED."))
    return findings


# ---------------------------------------------------------------------------
# (2) KIE PROVENANCE — a real kie.ai taskId per rendered slide in the manifest.
# ---------------------------------------------------------------------------
def check_kie_provenance(run_dir):
    """AF-NOT-KIE-RENDERED. Require that the process manifest's render record maps every
    slide to a REAL kie.ai taskId (not native / placeholder / empty). Mirrors the
    on-disk signal build_deck.write_process_manifest emits. Returns "" on pass, else a
    reason. A run dir with no render record / no taskIds means the images were NOT
    kie-rendered."""
    run_dir = Path(run_dir)
    pm = run_dir / "working" / "checkpoints" / "process_manifest.json"
    if not pm.is_file():
        return (f"{AF_NOT_KIE_RENDERED}: no working/checkpoints/process_manifest.json — the "
                "deck carries NO kie.ai render record, so not one slide can be proven "
                "kie-baked. A canonical deck records a kie taskId per slide.")
    obj = _load_json(pm)
    if not isinstance(obj, dict):
        return (f"{AF_NOT_KIE_RENDERED}: process_manifest.json is unreadable / not JSON — "
                "kie provenance cannot be proven (fail-closed).")
    phases = obj.get("phases")
    recs = [p for p in phases if isinstance(p, dict) and p.get("phase") == "render"] \
        if isinstance(phases, list) else []
    if not recs:
        return (f"{AF_NOT_KIE_RENDERED}: process_manifest.json carries no phase=='render' "
                "record written by build_deck.py — these slides were never baked via kie.ai.")
    rec = recs[-1]
    slides = rec.get("slides")
    if not isinstance(slides, list) or not slides:
        return (f"{AF_NOT_KIE_RENDERED}: the render record carries no per-slide entries — no "
                "slide maps to a kie.ai taskId.")
    bad, real = [], 0
    for entry in slides:
        if not isinstance(entry, dict):
            bad.append("a per-slide entry is malformed (not an object)")
            continue
        tid = entry.get("taskId")
        norm = tid.strip().lower() if isinstance(tid, str) else tid
        if norm in _BAD_TASK_IDS:
            bad.append(f"slide {entry.get('slide')!r}: taskId={tid!r} is not a real kie task id")
        else:
            real += 1
    if real == 0:
        return (f"{AF_NOT_KIE_RENDERED}: NO slide carries a real kie.ai taskId — the images "
                "were not kie-rendered (native / placeholder render). " + "; ".join(bad[:6]))
    if bad:
        return (f"{AF_NOT_KIE_RENDERED}: one or more slides lack a real kie.ai taskId — "
                + "; ".join(bad[:6]))
    return ""


# ---------------------------------------------------------------------------
# Governed-run-dir resolution + owner-skip token (the ONLY bypass).
# ---------------------------------------------------------------------------
def _is_governed(d):
    return (d is not None and Path(d).is_dir()
            and (Path(d) / "working" / "checkpoints" / "process_manifest.json").is_file())


def _resolve_governed_run_dir(artifact_path, run_dir):
    """Return the governed run dir for this artifact, or None. A governed run dir
    carries working/checkpoints/process_manifest.json. Prefer an explicit governed
    run_dir; else walk up from the artifact (the client package lives at
    run_dir/delivery/[slug]-FINAL/). None => no governed run dir => fail-closed."""
    if _is_governed(run_dir):
        return Path(run_dir)
    try:
        cur = Path(artifact_path).resolve().parent
    except Exception:  # noqa: BLE001
        return None
    for _ in range(8):
        if _is_governed(cur):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _coerce_owner_skip(raw):
    out = {}
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return out
    for rec in raw:
        if not isinstance(rec, dict):
            continue
        approved = rec.get("owner_approved") is True or rec.get("approved") is True
        gate = rec.get("gate") or rec.get("af_code") or rec.get("phase_id")
        if (approved and gate
                and str(rec.get("approved_by", "")).strip()
                and str(rec.get("reason", "")).strip()):
            out[str(gate)] = rec
    return out


def _load_owner_skips(run_dir, artifact_path=None):
    """Load logged owner_skip_approval tokens. Reuses the audited canonical_render_guard
    loader for the governed run dir, and ALSO honors an owner_skip_approval.json placed
    adjacent to an out-of-pipeline artifact (so an owner can authorize an out-of-band
    delivery with a logged, audited token even when there is no run dir). A malformed /
    owner_approved:false token authorizes nothing."""
    skips = {}
    if run_dir is not None:
        try:
            import canonical_render_guard as crg  # noqa: WPS433
            skips.update(crg.load_owner_skip_approvals(Path(run_dir)))
        except Exception:  # noqa: BLE001
            pm = Path(run_dir) / "working" / "checkpoints" / "process_manifest.json"
            obj = _load_json(pm) or {}
            skips.update(_coerce_owner_skip(
                obj.get("owner_skip_approval", obj.get("owner_skip_approvals", []))))
    if artifact_path is not None:
        adj = Path(artifact_path).resolve().parent / "owner_skip_approval.json"
        if adj.is_file():
            obj = _load_json(adj)
            if isinstance(obj, dict):
                skips.update(_coerce_owner_skip(
                    obj.get("owner_skip_approval", obj.get("owner_skip_approvals", obj))))
            else:
                skips.update(_coerce_owner_skip(obj))
    return skips


def _lead_af_code(reason):
    m = re.match(r"\s*(AF-[A-Z0-9]+(?:-[A-Z0-9]+)*)", reason)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# (4) BUNDLE-COMPLETENESS — the FULL deliverable set must be present.
# ---------------------------------------------------------------------------
def _bundle_completeness(run_dir, *, verify_destinations: bool = True):
    """Require the full deliverable set before delivery: the five-file client package
    (deck pptx + deck pdf + presenter guide + presenter speech + audio, via AF-DH1),
    the GoHighLevel upload record + destination ground-truth (via delivery_gate), AND
    the teleprompter deliverable. A bare run dir at the delivery boundary that never
    assembled a package/plan is INCOMPLETE (this is the 1-of-12 partial-delivery
    failure). Returns a list of AF-coded reasons.

    verify_destinations=False is the PRE-TRANSPORT subset (used when the boundary gate
    runs INSIDE a transport — ghl_media_push.py / the SOP copy step — BEFORE the upload):
    the AF-DH1 five-file package + teleprompter are still required, but the SOP-9.4
    destination ground-truth (the GHL upload record / mac anchor) is skipped, because
    that upload is exactly what the transport is ABOUT to perform — verifying it
    pre-upload would be circular. The artifact-intrinsic gates (overlay / kie / no-run-
    dir) are unaffected and still fully apply in gate_delivered_artifact."""
    run_dir = Path(run_dir)
    reasons = []
    # delivery_gate() returns (True, []) for BOTH a clean-complete delivery AND a
    # pre-delivery DEFER (no package AND no plan). At the delivery boundary a deck is
    # being shipped, so a DEFER means the bundle was never assembled — REJECT it.
    pkg = find_client_package(run_dir)
    plan_exists = (run_dir / "working" / "checkpoints" / "delivery_plan.json").is_file()
    if pkg is None and not plan_exists:
        reasons.append(f"{AF_BUNDLE_COMPLETE}: a deck artifact is being delivered but no "
                       "delivery/[DECK_SLUG]-FINAL/ client package and no delivery_plan.json "
                       "exist — the full deliverable set (deck + presenter speech + audio + "
                       "presenter guide + teleprompter + GoHighLevel upload record) was "
                       "never assembled. REJECTED.")
    else:
        _ok, dg = delivery_gate(run_dir, verify_destinations=verify_destinations)
        reasons.extend(dg)
    # Teleprompter sibling (part of the full presentation experience).
    tele = []
    for pat in ("**/*teleprompter*.html", "**/*TELEPROMPTER*.html",
                "**/*teleprompter*.pdf", "**/*TELEPROMPTER*.pdf"):
        tele.extend(run_dir.glob(pat))
    if not tele:
        reasons.append(f"{AF_BUNDLE_COMPLETE}: the teleprompter deliverable "
                       "(teleprompter*.html/pdf) is absent from the run dir — the full "
                       "presentation experience is incomplete. REJECTED.")
    return reasons


# ---------------------------------------------------------------------------
# THE BOUNDARY GATE — fail-closed, runs for EVERY deck regardless of how produced.
# ---------------------------------------------------------------------------
def gate_delivered_artifact(artifact_path, run_dir=None, *, verify_destinations: bool = True):
    """FAIL-CLOSED delivery boundary gate over the SHIPPED ARTIFACT. Returns
    (ok, reasons). ok is False on any unwaived rejection. Inspects the artifact itself
    (selectable text / kie provenance / bundle completeness) so a hand-built or overlay
    deck cannot be delivered no matter how it was produced. The ONLY bypass is a logged
    owner_skip_approval token (gate=<AF code>); an agent may NOT self-approve.

    verify_destinations defaults to True (the full delivery-boundary check, e.g. at
    run_signature_deck.py P9-DELIVER, where the uploads have already happened). Call it
    with verify_destinations=False from a TRANSPORT (ghl_media_push.py before it uploads
    a deck, or the SOP copy/send step) so the gate runs BEFORE the deck leaves the box:
    every artifact-intrinsic gate (AF-OVERLAY-DELIVERED / AF-NOT-KIE-RENDERED /
    AF-NO-RUN-DIR) plus the AF-DH1 five-file package + teleprompter are enforced, while
    the SOP-9.4 destination ground-truth (the very upload the transport is about to do)
    is deferred — so a hand-built / overlay / no-run-dir deck is REJECTED at the
    transport without the chicken-and-egg of demanding the upload record before the
    upload."""
    artifact_path = Path(artifact_path)
    if not artifact_path.is_file():
        return False, [f"{AF_NO_RUN_DIR}: delivery artifact does not exist: {artifact_path}"]
    suffix = artifact_path.suffix.lower()
    if suffix not in (".pptx", ".pdf"):
        return False, [f"{AF_NOT_KIE_RENDERED}: delivery artifact is not a .pptx/.pdf deck: "
                       f"{artifact_path.name} (fail-closed)."]

    resolved = _resolve_governed_run_dir(artifact_path, run_dir)
    owner_skips = _load_owner_skips(resolved, artifact_path)

    def waived(code):
        return code in owner_skips

    reasons = []

    # (3) NO-RUN-DIR FAIL-CLOSED — a deck with no governed run dir was hand-built
    # OUTSIDE run_signature_deck.py. This is the flip of the legacy pre-delivery defer.
    if resolved is None:
        if not waived(AF_NO_RUN_DIR):
            return False, [
                f"{AF_NO_RUN_DIR}: no governed run dir "
                "(working/checkpoints/process_manifest.json) could be resolved for "
                f"{artifact_path.name}. A deck with no governed run dir was hand-built "
                "OUTSIDE run_signature_deck.py and CANNOT be delivered. The only bypass is "
                "a logged owner_skip_approval token (gate=AF-NO-RUN-DIR)."]
        reasons.append(f"NOTE: {AF_NO_RUN_DIR} waived by logged owner_skip_approval.")

    # (1) ARTIFACT PROVENANCE — selectable-text / unreadable-artifact inspection.
    prov = inspect_pptx_artifact(artifact_path) if suffix == ".pptx" \
        else inspect_pdf_artifact(artifact_path)
    for code, reason in prov:
        if waived(code):
            reasons.append(f"NOTE: {code} waived by owner_skip_approval.")
        else:
            reasons.append(reason)

    # (2) KIE PROVENANCE + (4) BUNDLE — require a governed run dir to evaluate.
    if resolved is not None:
        kie = check_kie_provenance(resolved)
        if kie:
            reasons.append(f"NOTE: {AF_NOT_KIE_RENDERED} waived by owner_skip_approval."
                           if waived(AF_NOT_KIE_RENDERED) else kie)
        for r in _bundle_completeness(resolved, verify_destinations=verify_destinations):
            code = _lead_af_code(r) or AF_BUNDLE_COMPLETE
            if waived(code) or waived(AF_BUNDLE_COMPLETE):
                reasons.append(f"NOTE: {code} waived by owner_skip_approval.")
            else:
                reasons.append(r)

    hard = [r for r in reasons if not r.startswith("NOTE")]
    return (len(hard) == 0), reasons


def delivery_gate(run_dir: Path, *, verify_destinations: bool = True):
    """Mechanical last-mile gate. Returns (ok, reasons). Defers (ok=True, []) when no
    delivery has been attempted yet (no package dir AND no delivery_plan.json).

    verify_destinations=False runs the PRE-TRANSPORT subset: AF-DH1 package hygiene + any
    recorded af_dh1_triggered flag, but SKIPS the SOP-9.4 destination ground-truth (the
    GHL upload record / mac anchor / drive ids) and the "no delivery_plan.json yet"
    complaint — because when the boundary gate fires INSIDE a transport (before the
    upload/copy), those destinations are exactly what is about to be written, so
    verifying them first would be circular."""
    run_dir = Path(run_dir)
    plan_path = run_dir / "working" / "checkpoints" / "delivery_plan.json"
    pkg = find_client_package(run_dir)
    plan_exists = plan_path.is_file()

    if pkg is None and not plan_exists:
        return True, []  # pre-delivery render — defer.

    if isinstance(pkg, list):
        return False, [f"AF-DH1: more than one *-FINAL client package under delivery/: "
                       f"{', '.join(p.name for p in pkg)}"]

    reasons = []
    if pkg is None:
        reasons.append("AF-DH1: a delivery_plan.json exists but no delivery/[DECK_SLUG]-FINAL/ "
                       "client package was assembled")
    else:
        dh1 = check_af_dh1(pkg)
        if dh1:
            reasons.append(dh1)

    if plan_exists:
        plan = _load_json(plan_path)
        if plan is None:
            reasons.append("SOP-9.4: working/checkpoints/delivery_plan.json is unreadable / not JSON")
        else:
            if plan.get("af_dh1_triggered"):
                reasons.append(f"AF-DH1: delivery_plan records af_dh1_triggered: "
                               f"{plan.get('af_dh1_details', 'unspecified')}")
            if verify_destinations:
                reasons.extend(_check_destinations(run_dir, plan))
    elif verify_destinations:
        reasons.append("SOP-9.4: client package exists but no delivery_plan.json "
                       "(destination resolution never ran)")

    return (len(reasons) == 0), reasons


# ---------------------------------------------------------------------------
# SELF-TEST — built-in pass + fail fixtures (no external deps, no network).
# ---------------------------------------------------------------------------
def _mk_pkg(base: Path, files):
    d = base / "delivery" / "demo-deck-FINAL"
    d.mkdir(parents=True, exist_ok=True)
    for nm in files:
        (d / nm).write_text("x")
    return d


def _write_plan(base: Path, plan):
    p = base / "working" / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    (p / "delivery_plan.json").write_text(json.dumps(plan))


def _write_media(base: Path, media):
    p = base / "working" / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    (p / "media_library.json").write_text(json.dumps(media))


FIVE = ["demo-deck-FINAL.pptx", "demo-deck-FINAL.pdf", "PRESENTER-GUIDE.pdf",
        "PRESENTERS-SPEECH.pdf", "PRESENTER-AUDIO.mp3"]

_SLIDE_IMG_ONLY = (
    '<?xml version="1.0"?><p:sld xmlns:p="x" xmlns:a="y"><p:cSld><p:spTree>'
    '<p:pic><p:blipFill><a:blip r:embed="rId2"/></p:blipFill></p:pic>'
    '</p:spTree></p:cSld></p:sld>')
_SLIDE_WITH_TEXT = (
    '<?xml version="1.0"?><p:sld xmlns:p="x" xmlns:a="y"><p:cSld><p:spTree>'
    '<p:sp><p:txBody><a:p><a:r><a:t>Hand-built headline overlay</a:t></a:r>'
    '</a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>')


def _mk_pptx(path: Path, with_text: bool):
    """Write a minimal OOXML .pptx zip with one slide part — image-only or with a
    selectable <a:t> text run — using stdlib zipfile only (no python-pptx)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(path), "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("ppt/slides/slide1.xml",
                    _SLIDE_WITH_TEXT if with_text else _SLIDE_IMG_ONLY)
    return path


def _write_render_manifest(base: Path, task_ids):
    """Write a process_manifest.json render record with the given per-slide taskIds."""
    p = base / "working" / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    rec = {"phase": "render", "output_slide_count": len(task_ids),
           "slides": [{"slide": i + 1, "taskId": t} for i, t in enumerate(task_ids)]}
    (p / "process_manifest.json").write_text(json.dumps({"phases": [rec]}))


def _mk_full_run(base: Path, with_text=False, task_ids=("kie-1",), teleprompter=True):
    """Assemble a complete governed run dir: 5-file client package (deck.pptx baked as
    an OOXML zip), GHL upload record + plan, a render manifest with kie taskIds, and a
    teleprompter. Returns the path to the delivered deck .pptx."""
    pkg = base / "delivery" / "demo-deck-FINAL"
    pkg.mkdir(parents=True, exist_ok=True)
    deck = _mk_pptx(pkg / "demo-deck-FINAL.pptx", with_text=with_text)
    for nm in ("demo-deck-FINAL.pdf", "PRESENTER-GUIDE.pdf",
               "PRESENTERS-SPEECH.pdf", "PRESENTER-AUDIO.mp3"):
        (pkg / nm).write_text("x")
    _write_media(base, {"pptx_ghl_media_id": "gid"})
    _write_plan(base, {"destinations": [
        {"type": "ghl", "status": "uploaded"},
        {"type": "mac_downloads", "verify_anchor": str(deck)},
    ]})
    _write_render_manifest(base, list(task_ids))
    if teleprompter:
        tp = base / "working" / "teleprompter"
        tp.mkdir(parents=True, exist_ok=True)
        (tp / "teleprompter.html").write_text("<html></html>")
    return deck


def _selftest() -> int:
    fails = []

    # CASE A — pre-delivery render (nothing) -> DEFER (ok, no reasons).
    with tempfile.TemporaryDirectory() as t:
        ok, reasons = delivery_gate(Path(t))
        if not ok or reasons:
            fails.append(f"A defer: expected ok/empty, got ok={ok} reasons={reasons}")

    # CASE B — clean 5-file package + verified GHL + mac anchor -> PASS.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        pkg = _mk_pkg(base, FIVE)
        _write_media(base, {"pptx_ghl_media_id": "abc123"})
        _write_plan(base, {"destinations": [
            {"type": "ghl", "ghl_folder_id": "root", "status": "uploaded"},
            {"type": "mac_downloads", "verify_anchor": str(pkg / "demo-deck-FINAL.pptx")},
        ]})
        ok, reasons = delivery_gate(base)
        if not ok:
            fails.append(f"B pass: expected PASS, got reasons={reasons}")

    # CASE C — extra .md draft in the package -> AF-DH1 FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        pkg = _mk_pkg(base, FIVE + ["notes-draft.md"])
        _write_media(base, {"pptx_ghl_media_id": "abc"})
        _write_plan(base, {"destinations": [{"type": "ghl"}]})
        ok, reasons = delivery_gate(base)
        if ok or not any("AF-DH1" in r for r in reasons):
            fails.append(f"C extra-md: expected AF-DH1 FAIL, got ok={ok} reasons={reasons}")

    # CASE D — singular legacy speech name in client package -> AF-DH1 FAIL (whitelist plural).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        bad_five = ["demo-deck-FINAL.pptx", "demo-deck-FINAL.pdf", "PRESENTER-GUIDE.pdf",
                    "PRESENTER-SPEECH.pdf", "PRESENTER-AUDIO.mp3"]
        _mk_pkg(base, bad_five)
        _write_media(base, {"pptx_ghl_media_id": "abc"})
        _write_plan(base, {"destinations": [{"type": "ghl"}]})
        ok, reasons = delivery_gate(base)
        if ok or not any("AF-DH1" in r for r in reasons):
            fails.append(f"D singular-speech: expected AF-DH1 FAIL, got ok={ok} reasons={reasons}")

    # CASE E — ghl destination but NO upload record -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _mk_pkg(base, FIVE)
        _write_media(base, {})  # no pptx_ghl_media_id
        _write_plan(base, {"destinations": [{"type": "ghl", "status": "pending"}]})
        ok, reasons = delivery_gate(base)
        if ok or not any("pptx_ghl_media_id" in r for r in reasons):
            fails.append(f"E no-upload-record: expected GHL FAIL, got ok={ok} reasons={reasons}")

    # CASE F — mac_downloads verify_anchor missing on disk -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _mk_pkg(base, FIVE)
        _write_plan(base, {"destinations": [
            {"type": "mac_downloads", "verify_anchor": str(base / "delivery" / "nope.pptx")},
        ]})
        ok, reasons = delivery_gate(base)
        if ok or not any("verify_anchor missing" in r for r in reasons):
            fails.append(f"F missing-anchor: expected SOP-9.4 FAIL, got ok={ok} reasons={reasons}")

    # CASE G — package incomplete (missing audio) -> AF-DH1 FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _mk_pkg(base, FIVE[:-1])  # no audio
        _write_plan(base, {"destinations": [{"type": "ghl"}]})
        _write_media(base, {"pptx_ghl_media_id": "abc"})
        ok, reasons = delivery_gate(base)
        if ok or not any("AF-DH1" in r and "missing" in r for r in reasons):
            fails.append(f"G incomplete: expected AF-DH1 missing FAIL, got ok={ok} reasons={reasons}")

    # === OUT-OF-BAND BOUNDARY GATE (gate_delivered_artifact) ===

    # CASE H — clean image-only deck + full governed run dir -> PASS.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = _mk_full_run(base, with_text=False, task_ids=("kie-aaa", "kie-bbb"))
        # render manifest has 2 slides but package deck has 1 — align taskIds to 1.
        _write_render_manifest(base, ["kie-aaa"])
        ok, reasons = gate_delivered_artifact(deck, base)
        if not ok:
            fails.append(f"H boundary-pass: expected PASS, got {reasons}")

    # CASE H2 — selectable native on-slide text -> AF-OVERLAY-DELIVERED REJECT.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = _mk_full_run(base, with_text=True, task_ids=("kie-aaa",))
        ok, reasons = gate_delivered_artifact(deck, base)
        if ok or not any("AF-OVERLAY-DELIVERED" in r for r in reasons):
            fails.append(f"H2 overlay: expected AF-OVERLAY-DELIVERED REJECT, got ok={ok} {reasons}")

    # CASE I — no governed run dir (deck in a bare dir) -> AF-NO-RUN-DIR REJECT.
    with tempfile.TemporaryDirectory() as t:
        deck = _mk_pptx(Path(t) / "loose-deck.pptx", with_text=False)
        ok, reasons = gate_delivered_artifact(deck, None)
        if ok or not any("AF-NO-RUN-DIR" in r for r in reasons):
            fails.append(f"I no-run-dir: expected AF-NO-RUN-DIR REJECT, got ok={ok} {reasons}")

    # CASE J — render record with a native (non-kie) taskId -> AF-NOT-KIE-RENDERED.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = _mk_full_run(base, with_text=False, task_ids=("kie-aaa",))
        _write_render_manifest(base, ["native"])  # not a real kie bake
        ok, reasons = gate_delivered_artifact(deck, base)
        if ok or not any("AF-NOT-KIE-RENDERED" in r for r in reasons):
            fails.append(f"J not-kie: expected AF-NOT-KIE-RENDERED REJECT, got ok={ok} {reasons}")

    # CASE K — missing teleprompter sibling -> AF-BUNDLE-COMPLETE REJECT.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = _mk_full_run(base, with_text=False, task_ids=("kie-aaa",), teleprompter=False)
        ok, reasons = gate_delivered_artifact(deck, base)
        if ok or not any("AF-BUNDLE-COMPLETE" in r and "teleprompter" in r for r in reasons):
            fails.append(f"K bundle: expected AF-BUNDLE-COMPLETE teleprompter REJECT, got ok={ok} {reasons}")

    # CASE L — owner_skip_approval waives the no-run-dir block (the ONLY bypass).
    with tempfile.TemporaryDirectory() as t:
        deck = _mk_pptx(Path(t) / "loose-deck.pptx", with_text=False)
        (Path(t) / "owner_skip_approval.json").write_text(json.dumps({
            "owner_approved": True, "gate": "AF-NO-RUN-DIR",
            "approved_by": "owner", "reason": "audited out-of-band delivery"}))
        ok, reasons = gate_delivered_artifact(deck, None)
        if not ok:
            fails.append(f"L owner-skip: expected PASS via owner_skip_approval, got {reasons}")

    # CASE M — a non-zip / decoy .pptx -> AF-NOT-KIE-RENDERED (fail-closed).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _mk_full_run(base, with_text=False, task_ids=("kie-aaa",))
        decoy = base / "delivery" / "demo-deck-FINAL" / "demo-deck-FINAL.pptx"
        decoy.write_bytes(b"\x89PNG not a real pptx")  # a renamed image, not OOXML
        ok, reasons = gate_delivered_artifact(decoy, base)
        if ok or not any("AF-NOT-KIE-RENDERED" in r for r in reasons):
            fails.append(f"M decoy: expected AF-NOT-KIE-RENDERED REJECT, got ok={ok} {reasons}")

    # === PRE-TRANSPORT MODE (verify_destinations=False) — the gate the transport runs ===

    # CASE N — PRE-TRANSPORT: a clean governed deck whose GHL upload has NOT happened
    # yet (no pptx_ghl_media_id, plan ghl destination still pending). It MUST PASS the
    # pre-transport gate (the upload is what the transport is about to do) while the FULL
    # gate FAILS on the missing upload record — proving the transport gate is not
    # chicken-and-egg yet stays fail-closed on real provenance.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = _mk_full_run(base, with_text=False, task_ids=("kie-aaa",))
        _write_render_manifest(base, ["kie-aaa"])
        _write_media(base, {})  # GHL upload record not written yet (transport pending)
        _write_plan(base, {"destinations": [
            {"type": "ghl", "status": "pending"},
            {"type": "mac_downloads", "verify_anchor": str(deck)},
        ]})
        ok_pre, r_pre = gate_delivered_artifact(deck, base, verify_destinations=False)
        if not ok_pre:
            fails.append(f"N pre-transport-pass: expected PASS pre-transport, got {r_pre}")
        ok_full, r_full = gate_delivered_artifact(deck, base, verify_destinations=True)
        if ok_full or not any("pptx_ghl_media_id" in r for r in r_full):
            fails.append(f"N full-fail: expected FULL gate to FAIL on missing upload "
                         f"record, got ok={ok_full} {r_full}")

    # CASE O — PRE-TRANSPORT still REJECTS a hand-built overlay deck: artifact provenance
    # is unaffected by verify_destinations, so a transport cannot ship an overlay deck.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = _mk_full_run(base, with_text=True, task_ids=("kie-aaa",))
        ok, reasons = gate_delivered_artifact(deck, base, verify_destinations=False)
        if ok or not any("AF-OVERLAY-DELIVERED" in r for r in reasons):
            fails.append(f"O pre-transport-overlay: expected AF-OVERLAY-DELIVERED REJECT, "
                         f"got ok={ok} {reasons}")

    if fails:
        print("delivery_gate selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("delivery_gate selftest -> PASS (16 cases: defer/pass/extra-md/singular/"
          "no-upload/missing-anchor/incomplete + boundary: clean-pass/overlay/no-run-dir/"
          "not-kie/bundle/owner-skip/decoy + pre-transport: upload-pending-pass/overlay-reject)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Mechanical last-mile delivery gate (R9-F9) "
                                 "+ out-of-band fail-closed delivery boundary gate.")
    ap.add_argument("run_dir", nargs="?", help="presentation run directory")
    ap.add_argument("--artifact", help="the SHIPPED deck artifact (.pptx/.pdf) to gate "
                    "at the delivery boundary (fail-closed)")
    ap.add_argument("--run-dir", dest="run_dir_opt", help="governed run dir for --artifact")
    ap.add_argument("--pre-transport", action="store_true",
                    help="PRE-TRANSPORT mode for --artifact: run the boundary gate BEFORE a "
                    "deck leaves the box (the SOP copy/upload step). Enforces artifact "
                    "provenance (AF-OVERLAY-DELIVERED / AF-NOT-KIE-RENDERED / AF-NO-RUN-DIR) "
                    "+ the AF-DH1 five-file package + teleprompter, but DEFERS the SOP-9.4 "
                    "destination ground-truth (the upload this transport is about to do). "
                    "Use this in delivery-concierge-sops.md before any cp/upload/send; the "
                    "full destination check runs later at run_signature_deck.py P9-DELIVER.")
    ap.add_argument("--selftest", action="store_true", help="run built-in fixtures")
    ap.add_argument("--json", action="store_true", help="emit JSON result")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    # OUT-OF-BAND BOUNDARY MODE — inspect the shipped artifact, fail-closed.
    if args.artifact:
        rd = args.run_dir_opt or args.run_dir
        ok, reasons = gate_delivered_artifact(args.artifact, rd,
                                              verify_destinations=not args.pre_transport)
        if args.json:
            print(json.dumps({"ok": ok, "reasons": reasons}, indent=2))
        else:
            if ok:
                print("DELIVERY BOUNDARY GATE: PASS (artifact provenance + kie + bundle clean)")
                for r in reasons:
                    print("  -", r)  # NOTEs (owner-skip waivers) surface here.
            else:
                print("DELIVERY BOUNDARY GATE: REJECTED")
                for r in reasons:
                    print("  -", r)
        return 0 if ok else 1

    if not args.run_dir:
        ap.error("run_dir is required (or use --artifact / --selftest)")
    rd = Path(args.run_dir)
    if not rd.is_dir():
        print(f"delivery_gate: run_dir not a directory: {rd}", file=sys.stderr)
        return 2
    ok, reasons = delivery_gate(rd)
    if args.json:
        print(json.dumps({"ok": ok, "reasons": reasons}, indent=2))
    else:
        if ok:
            print("DELIVERY GATE: PASS (last mile complete or pre-delivery defer)")
        else:
            print("DELIVERY GATE: FAIL")
            for r in reasons:
                print("  -", r)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
