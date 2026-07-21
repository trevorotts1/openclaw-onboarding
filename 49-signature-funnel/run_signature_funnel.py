#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_signature_funnel.py — the deterministic Signature Funnel orchestrator (Skill 49).

A no-skip state machine. It runs the fixed phase spine P0..P9 IN ORDER, shells each
phase's fail-closed prover, and — only when EVERY phase passes — emits a signed
PROCESS-CERTIFICATE.json. A failing gate aborts the run (fail-closed) and NO certificate
is written, so an incomplete or non-compliant funnel can never reach Complete.

FRONT-DOOR NONCE (required): the canonical entry shell (signature-funnel-entry.sh) writes
a run-scoped 0600 nonce file and passes its value with --nonce. The orchestrator refuses
to run unless the supplied nonce matches the file — a direct `python3 run_signature_funnel.py`
without the front-door nonce dies with AF-FUN-FRONT-DOOR. The same nonce keys the
certificate HMAC, so a certificate can only be minted by a real front-door run.

DELEGATION SEAMS (never forked here): image generation is delegated to Skill 47
(kie_image.py); GHL media folder + upload and the funnel/page build are delegated to
Skill 6 (ghl_media.py / ghl_rest_canvas.py). Those phases are attested in order; the
image PROVENANCE (Kie taskId + GHL media host) is enforced at P9 by prove_sf_no_pitch.py.

Run-dir inputs:
  brief.json          — locked intake brief        (P0 gate: prove_sf_intake.py)
  copy_ledger.json    — per-page 12-section copy    (P1 gate: prove_sf_copy.py)
  prompt_ledger.json  — image prompts 5k-19k        (P2 gate: prove_sf_prompt_floor.py)
  media_ledger.json   — images + pages              (P9 gate: prove_sf_no_pitch.py)

stdlib only. Exit 0 = certified, 2 = a phase gate failed, 3 = front-door / usage.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SCRIPTS = _SCRIPT_DIR / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import prove_sf_cert  # noqa: E402  (shared cert schema + HMAC signing; guarantees agreement)
import prove_sf_graph  # noqa: E402  (P5/P8 page matrix + P6 graph gate; one source of truth)
import prove_sf_build  # noqa: E402  (P7 build-receipt gate)

EXIT_OK = 0
EXIT_GATE_FAIL = 2
EXIT_FRONT_DOOR = 3

PY = sys.executable or "python3"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _shell_prover(script: str, args: List[str]) -> Tuple[bool, str]:
    """Run a prover as a subprocess. pass == returncode 0."""
    path = _SCRIPTS / script
    if not path.exists():
        return False, f"prover {script} not found at {path}"
    proc = subprocess.run([PY, str(path), *args], capture_output=True, text=True)
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    detail = tail[-1] if tail else f"rc={proc.returncode}"
    return proc.returncode == 0, f"{script} rc={proc.returncode} :: {detail}"


def _delegation_seam(run_dir: Path, required_file: Optional[str], label: str) -> Tuple[bool, str]:
    """A phase that is delegated to another skill. If a prerequisite artifact is named it
    MUST exist (fail-closed); otherwise the seam is attested as delegated.

    A10 / T0-09 — file EXISTENCE is no longer accepted as proof of delegation on its own.
    This helper remains for seams with no content contract; the image/media seams now go
    through _gate_p3_images / _gate_p4_media, which read the ledger's content and consult
    the provider-receipt store."""
    if required_file is not None:
        p = run_dir / required_file
        if not p.exists():
            return False, f"delegated artifact {required_file} absent (expected for: {label})"
    return True, f"delegated: {label}"


# ---------------------------------------------------------------------------
# A10 / T0-09 — the delegated image + media seams.
#
# THE DEFECT: P3-IMAGES and P4-MEDIA attested "delegated" the moment
# media_ledger.json EXISTED. The run writes that file, so the phase claiming to
# prove image generation through Skill 47 and upload through Skill 6 was
# satisfied by a file its own subject authored — with no provider ever contacted.
#
# THE FIX, IN TWO LANDINGS (sequencing: writer before requirer):
#   (this release) the seams read the ledger's CONTENT — every image record must
#     carry a real provider task id (P3) and resolve to a GHL media host (P4) —
#     and any provider receipt that IS present must hold, strictly. Both content
#     rules already gate P9 via prove_sf_no_pitch, so no run that could certify
#     before can fail now: this only moves the truth forward to the phase that
#     claims it, and kills "the file exists, therefore a provider ran".
#   (next)         delegation_receipt.require() replaces validate_if_present()
#     once Skill 47 / Skill 6 emit a receipt on every path. The certificate
#     records which of the two states applied, so it can never imply
#     provider-backed delegation it does not have.
# ---------------------------------------------------------------------------
_GHL_HOST_FINGERPRINTS = ("gohighlevel", "leadconnector", "leadconnectorhq", "msgsndr",
                          "highlevel", "storage.googleapis.com/highlevel")
_BAD_TASK_IDS = frozenset({"", "native", "placeholder", "none", "null", "n/a", "tbd", "todo"})


def _ledger_images(run_dir: Path) -> Tuple[Optional[List[Dict]], str]:
    p = run_dir / "media_ledger.json"
    if not p.exists():
        return None, "media_ledger.json absent"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return None, f"media_ledger.json unreadable ({exc})"
    imgs = data.get("images") if isinstance(data, dict) else None
    if not isinstance(imgs, list) or not imgs:
        return None, "media_ledger.json carries no non-empty 'images' array"
    return [i for i in imgs if isinstance(i, dict)], ""


def _image_key(img: Dict) -> str:
    """The identifier a provider receipt must cover for this ledger row."""
    return str(img.get("kie_task_id") or img.get("task_id")
               or f"{img.get('page_type', '?')}/{img.get('section', '?')}")


def _receipt_seam(run_dir: Path, phase: str, keys: List[str], label: str,
                  content_detail: str) -> Tuple[bool, str]:
    try:
        import delegation_receipt
    except ImportError as exc:  # noqa: BLE001 — a missing contract module is fail-closed
        return False, (f"AF-FUN-DELEG-RECEIPT: delegation_receipt.py is not importable "
                       f"({exc}) — the delegated seam {phase} cannot be attested")
    ok, detail, state = delegation_receipt.validate_if_present(
        run_dir, phase, must_cover=keys, af="AF-FUN-DELEG-RECEIPT")
    if not ok:
        return False, detail
    return True, f"delegated: {label} :: {content_detail} :: receipts {state} ({detail})"


def _gate_p3_images(run_dir: Path) -> Tuple[bool, str]:
    """P3-IMAGES — every ledger image must name a real image-provider task id."""
    imgs, err = _ledger_images(run_dir)
    if imgs is None:
        return False, f"AF-FUN-DELEG-IMAGES: {err} (Skill 47 kie_image.py produced nothing)"
    bad = []
    for img in imgs:
        tid = img.get("kie_task_id", img.get("task_id"))
        norm = str(tid).strip().lower() if tid is not None else ""
        if tid is None or norm in _BAD_TASK_IDS:
            bad.append(f"{img.get('page_type', '?')}/{img.get('section', '?')}={tid!r}")
    if bad:
        return False, (f"AF-FUN-DELEG-IMAGES: {len(bad)} image record(s) carry no real "
                       f"image-provider task id (e.g. {bad[:3]}) — an image nothing was "
                       "generated for is not a delegated result")
    return _receipt_seam(run_dir, "P3-IMAGES", [_image_key(i) for i in imgs],
                         "Skill 47 kie_image.py (text-to-image + reference_images hook)",
                         f"{len(imgs)} image record(s) carry a provider task id")


def _gate_p4_media(run_dir: Path) -> Tuple[bool, str]:
    """P4-MEDIA — every ledger image must resolve to a GHL media host."""
    imgs, err = _ledger_images(run_dir)
    if imgs is None:
        return False, f"AF-FUN-DELEG-MEDIA: {err} (Skill 6 ghl_media.py uploaded nothing)"
    bad = []
    for img in imgs:
        url = str(img.get("media_url", img.get("ghl_media_url", img.get("url", "")))).strip()
        hay = url.lower()
        if not hay.startswith(("http://", "https://")) or not any(
                fp in hay for fp in _GHL_HOST_FINGERPRINTS):
            bad.append(f"{img.get('page_type', '?')}/{img.get('section', '?')}={url!r}")
    if bad:
        return False, (f"AF-FUN-DELEG-MEDIA: {len(bad)} image record(s) do not resolve to a "
                       f"GHL media host (e.g. {bad[:3]}) — an un-uploaded image is not a "
                       "delegated upload")
    return _receipt_seam(run_dir, "P4-MEDIA", [_image_key(i) for i in imgs],
                         "Skill 6 ghl_media.py (media folder + upload)",
                         f"{len(imgs)} image record(s) on a GHL media host")


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _delegation_receipt_state(run_dir: Path) -> str:
    """'present' / 'absent' / 'malformed' — recorded on the certificate so a reader
    can tell whether the delegated phases were receipt-backed (A10 / T0-09)."""
    try:
        import delegation_receipt
        return delegation_receipt.store_state(run_dir)
    except Exception:  # noqa: BLE001 — a certificate field must never break certification
        return "unknown"


def _brief_size(run_dir: Path) -> Optional[int]:
    """Resolve the funnel size (3/5/7) from the locked brief, or None if unresolved."""
    try:
        size = json.loads((run_dir / "brief.json").read_text(encoding="utf-8")).get("funnel_size")
        return size if isinstance(size, int) else None
    except (ValueError, OSError):
        return None


def _gate_html_fragments(run_dir: Path) -> Tuple[bool, str]:
    """P5-HTML (FIX-XC-03a): a non-empty pages/<profile>.fragment.html for EVERY page
    in the brief's 3/5/7 matrix. No fragment set == no built pages == fail-closed."""
    size = _brief_size(run_dir)
    if size is None:
        return False, "AF-FUN-HTML-FRAGMENT: brief funnel_size unresolved — cannot prove page fragments (fail-closed)"
    try:
        pages = prove_sf_graph.funnel_pages(size)
    except (ValueError, OSError) as exc:
        return False, f"AF-FUN-HTML-FRAGMENT: cannot resolve the {size}-step page matrix ({exc})"
    missing: List[str] = []
    for profile in pages:
        frag = run_dir / "pages" / f"{profile}.fragment.html"
        try:
            body = frag.read_text(encoding="utf-8", errors="replace") if frag.exists() else ""
        except OSError:
            body = ""
        if not body.strip():
            missing.append(profile)
    if missing:
        return False, (f"AF-FUN-HTML-FRAGMENT: missing/empty pages/<profile>.fragment.html for "
                       f"{missing} (expected one per {size}-step matrix page)")
    return True, f"{len(pages)} page fragment(s) present + non-empty ({', '.join(pages)})"


def _gate_derived_pages(run_dir: Path) -> Tuple[bool, str]:
    """P8-DERIVE (FIX-XC-03a): a derived-page ledger (derived_pages.json) enumerating the
    U1/D1/U2/D2/TY pages required by the brief size. Absent/mismatched == fail-closed."""
    size = _brief_size(run_dir)
    if size is None:
        return False, "AF-FUN-DERIVE-LEDGER: brief funnel_size unresolved — cannot prove derived pages (fail-closed)"
    try:
        expected = prove_sf_graph.derived_pages(size)
    except (ValueError, OSError) as exc:
        return False, f"AF-FUN-DERIVE-LEDGER: cannot resolve the {size}-step derived set ({exc})"
    p = run_dir / "derived_pages.json"
    if not p.exists():
        return False, "AF-FUN-DERIVE-LEDGER: derived_pages.json absent (fail-closed)"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return False, f"AF-FUN-DERIVE-LEDGER: derived_pages.json unreadable ({exc})"
    entries = data.get("derived_pages") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        return False, "AF-FUN-DERIVE-LEDGER: derived_pages.json carries no non-empty 'derived_pages' array"
    got_ids = [str(e.get("id", "")).strip() for e in entries if isinstance(e, dict)]
    if sorted(got_ids) != sorted(expected):
        return False, (f"AF-FUN-DERIVE-LEDGER: derived set {got_ids} != required {expected} "
                       f"for the {size}-step funnel")
    for e in entries:
        want = prove_sf_graph.DERIVED_LABELS.get(str(e.get("id", "")).strip())
        got = str(e.get("label", "")).strip().upper()
        if want and got != want:
            return False, (f"AF-FUN-DERIVE-LEDGER: page {e.get('id')!r} labeled {got!r}, "
                           f"expected {want!r} (U1/D1/U2/D2/TY grammar)")
    return True, f"derived-page ledger lists {expected} (labels U1/D1/U2/D2/TY as required)"


def _gate_p2_prompts(run_dir: Path) -> Tuple[bool, str]:
    """P2-PROMPTS (FIX-IMG-07): the two-floor prompt gate AND the prompt COVERAGE
    cross-check. The floor gate proves each prompt that IS present is rich enough;
    the coverage assert proves the ledger carries a prompt for EVERY required
    (page_type, section) slot for the brief's funnel_size (per MASTERDOC §4) — so a
    2-prompt ledger can no longer clear P2 for a full funnel. Both must pass."""
    ok, detail = _shell_prover("prove_sf_prompt_floor.py",
                               ["--ledger", str(run_dir / "prompt_ledger.json")])
    if not ok:
        return ok, detail
    size = _brief_size(run_dir)
    if size is None:
        return False, ("AF-FUN-PROMPT-COVERAGE: brief funnel_size unresolved — cannot prove the "
                       "prompt coverage set (fail-closed)")
    cov_ok, cov_detail = _shell_prover(
        "prove_sf_prompt_floor.py",
        ["--structure", "--funnel-size", str(size), "--ledger", str(run_dir / "prompt_ledger.json")])
    if not cov_ok:
        return False, cov_detail
    return True, f"{detail} + prompt coverage complete ({cov_detail})"


def _gate_p9_certify(run_dir: Path) -> Tuple[bool, str]:
    """P9-CERTIFY (FIX-IMG-07): the no-pitch + image-provenance gate AND the image
    COVERAGE cross-check. prove_sf_no_pitch proves each shipped image is real; the
    coverage assert proves the media ledger carries an image for EVERY required
    (page_type, section) slot for the brief's funnel_size (per MASTERDOC §4) — so a
    2-image ledger can no longer certify a ~40-image funnel. Both must pass."""
    ok, detail = _shell_prover("prove_sf_no_pitch.py", ["--ledger", str(run_dir / "media_ledger.json")])
    if not ok:
        return ok, detail
    size = _brief_size(run_dir)
    if size is None:
        return False, ("AF-FUN-IMG-COVERAGE: brief funnel_size unresolved — cannot prove the image "
                       "coverage set (fail-closed)")
    cov_ok, cov_detail = _shell_prover(
        "prove_sf_prompt_floor.py",
        ["--structure", "--funnel-size", str(size), "--ledger", str(run_dir / "media_ledger.json")])
    if not cov_ok:
        return False, cov_detail
    return True, f"{detail} + image coverage complete ({cov_detail})"
# ---------------------------------------------------------------------------
# FAB-artifact producer + P7 FAB-scorecard requirement (FIX-COPY-02)
# ---------------------------------------------------------------------------
# The engine authors its copy in copy_ledger.json then delegates GHL delivery to
# Skill 6. On the engine-routed path Skill 6 produced NO template-match receipt, so
# the shared FAB-QC copy-substance gate (>=8.5) silently SKIPPED the flagship funnel.
# Here the engine ITSELF echoes copy_ledger.json into build/fab-artifact.json — the
# FAB scorecard file the QC seam scores — and P7-BUILD fail-closed REQUIRES that file
# to exist + carry real copy before it trusts the build receipt's QC>=8.5.

_FAB_ARTIFACT_REL = os.path.join("build", "fab-artifact.json")
# Copy-ledger keys that carry counts/metadata, never renderable copy.
_LEDGER_META_KEYS = frozenset({
    "section", "id", "page", "profile", "type", "order", "char_count",
    "word_count", "chars", "words", "count", "min", "max", "min_chars",
    "max_chars", "min_words", "max_words", "band", "ts", "at", "kind", "slug",
    "status", "funnel_type", "funnel_size", "has_cta_button", "personas",
    "offer_token_ledger", "product_title",
})


def _harvest_ledger_copy(node: object, bag: Dict[str, str], counter: List[int],
                         key_hint: str = "") -> None:
    """Flatten a copy_ledger page subtree into a {slot -> text} bag — every renderable
    string keyed by its nearest copy field name (self-contained; no external deps)."""
    if isinstance(node, str):
        t = node.strip()
        if t:
            slot = key_hint or f"copy{counter[0]}"
            if slot in bag:
                counter[0] += 1
                slot = f"{slot}-{counter[0]}"
            bag[slot] = t
    elif isinstance(node, (list, tuple)):
        for v in node:
            _harvest_ledger_copy(v, bag, counter, key_hint)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in _LEDGER_META_KEYS:
                continue
            _harvest_ledger_copy(v, bag, counter, str(k))


def _emit_fab_artifact_from_ledger(run_dir: Path) -> Optional[Path]:
    """Echo the engine copy_ledger.json into build/fab-artifact.json (the FAB scorecard
    file). Best-effort: returns the written path, or None when there is no readable copy
    ledger (P7 then fails closed on the missing FAB file — never a silent skip)."""
    led = run_dir / "copy_ledger.json"
    if not led.exists():
        return None
    try:
        cl = json.loads(led.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    pages_in = [p for p in (cl.get("pages") or []) if isinstance(p, dict)]
    pages: List[Dict] = []
    for i, pg in enumerate(pages_in):
        name = (pg.get("profile") or pg.get("page") or pg.get("name")
                or pg.get("id") or f"page-{i + 1}")
        bag: Dict[str, str] = {}
        _harvest_ledger_copy(pg.get("sections") if "sections" in pg else pg, bag, [0])
        pages.append({"name": str(name), "copy": bag})
    artifact = {
        "kind": "funnel",
        "funnel_template_id": cl.get("funnel_template_id"),
        "product_title": cl.get("product_title"),
        "flex_decision": "ROUTE_TO_ENGINE",
        "pages": pages,
        "source": "copy_ledger",
        "generated_by": "run_signature_funnel._emit_fab_artifact_from_ledger",
    }
    out = run_dir / _FAB_ARTIFACT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return out


def _gate_build(run_dir: Path) -> Tuple[bool, str]:
    """P7-BUILD (FIX-COPY-02): the QC>=8.5 seam now REQUIRES the FAB scorecard FILE.

    (1) build/fab-artifact.json MUST exist + carry copy-bearing pages — the un-fakeable
        proof the engine echoed the copy it authored (no artifact == fail-closed, never a
        silent FAB-QC skip).                                            -> AF-FUN-BUILD-FAB
    (2) THEN the pinned prove_sf_build.py enforces build_receipt.json QC>=8.5 + a preview
        URL per page (the existing seam)."""
    fab = run_dir / _FAB_ARTIFACT_REL
    if not fab.exists():
        return False, ("AF-FUN-BUILD-FAB: build/fab-artifact.json (the FAB scorecard) is "
                       "absent — the >=8.5 copy-substance gate cannot run (fail-closed). "
                       "The engine must echo copy_ledger.json into the FAB artifact.")
    try:
        art = json.loads(fab.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return False, f"AF-FUN-BUILD-FAB: build/fab-artifact.json is unreadable ({exc})"
    pages = art.get("pages") if isinstance(art, dict) else None
    if not isinstance(pages, list) or not pages:
        return False, "AF-FUN-BUILD-FAB: FAB artifact carries no non-empty 'pages' (nothing to score)"
    has_copy = any(
        isinstance(p, dict) and p.get("copy") and any(
            str(v).strip() for v in (p["copy"].values() if isinstance(p["copy"], dict)
                                     else [p["copy"]]))
        for p in pages
    )
    if not has_copy:
        return False, ("AF-FUN-BUILD-FAB: FAB artifact echoes NO copy — an un-echoed build "
                       "cannot be proven non-thin (fail-closed).")
    # A10 / T0-11: hand the prover the LOCKED brief size so it can compute the
    # required page-type set. Without it a 7-step funnel whose receipt supplies 3
    # pages returned zero violations. An unresolved size is fail-closed HERE rather
    # than letting the prover fall back to whatever the receipt declares about itself.
    size = _brief_size(run_dir)
    if size is None:
        return False, ("AF-FUN-BUILD-SIZE: brief funnel_size unresolved — the required "
                       "page-type set cannot be computed, so build completeness cannot be "
                       "proven (fail-closed)")
    ok, detail = _shell_prover("prove_sf_build.py",
                               ["--receipt", str(run_dir / "build_receipt.json"),
                                "--funnel-size", str(size)])
    if not ok:
        return False, detail
    return True, (f"FAB scorecard present ({len(pages)} page(s), copy echoed) + "
                  f"{size}-step page set complete + {detail}")


# Phase spine — ids + order MUST match prove_sf_cert.EXPECTED_PHASES.
def _phase_gates(run_dir: Path) -> List[Tuple[str, str, Callable[[], Tuple[bool, str]]]]:
    return [
        ("P0-INTAKE", "prove_sf_intake.py",
         lambda: _shell_prover("prove_sf_intake.py", [str(run_dir / "brief.json")])),
        ("P1-COPY", "prove_sf_copy.py",
         lambda: _shell_prover("prove_sf_copy.py", ["--ledger", str(run_dir / "copy_ledger.json")])),
        ("P2-PROMPTS", "prove_sf_prompt_floor.py",
         lambda: _gate_p2_prompts(run_dir)),
        ("P3-IMAGES", "kie_image.py",
         lambda: _gate_p3_images(run_dir)),
        ("P4-MEDIA", "ghl_media.py",
         lambda: _gate_p4_media(run_dir)),
        ("P5-HTML", "html_fragments",
         lambda: _gate_html_fragments(run_dir)),
        ("P6-COMPOSE", "prove_sf_graph.py",
         lambda: _shell_prover("prove_sf_graph.py", ["--graph", str(run_dir / "funnel_graph.json")])),
        ("P7-BUILD", "prove_sf_build.py",
         lambda: _gate_build(run_dir)),
        ("P8-DERIVE", "derived_pages_ledger",
         lambda: _gate_derived_pages(run_dir)),
        ("P9-CERTIFY", "prove_sf_no_pitch.py",
         lambda: _gate_p9_certify(run_dir)),
    ]


def _check_front_door(run_dir: Path, nonce: Optional[str], nonce_file: Optional[Path]) -> Tuple[bool, str]:
    nf = nonce_file or (run_dir / ".sf_run_nonce")
    if not nf.exists():
        return False, f"AF-FUN-FRONT-DOOR: no run-scoped nonce file at {nf} — run must start via signature-funnel-entry.sh"
    supplied = nonce if nonce is not None else os.environ.get("SF_RUN_NONCE")
    if not supplied:
        return False, "AF-FUN-FRONT-DOOR: no --nonce / SF_RUN_NONCE supplied (front-door nonce required)"
    on_disk = nf.read_text(encoding="utf-8").strip()
    if not on_disk or supplied.strip() != on_disk:
        return False, "AF-FUN-FRONT-DOOR: supplied nonce does not match the run-scoped nonce file"
    return True, supplied.strip()


def _resolve_persona(run_dir: Path) -> None:
    """F4.3 — resolve the funnel's canonical governing persona at the brief stage
    (best-effort; never blocks the run). Writes persona-selection.json for the copy
    prompts and the certificate. A bare box / unreachable selector is a clean skip."""
    try:
        sys.path.insert(0, str(_SCRIPTS))
        import persona_brief
        sel = persona_brief.resolve(run_dir)
        if sel:
            print(f"  [persona] {sel.get('persona_id')} ({sel.get('persona_name')}) "
                  f"via {sel.get('source')}")
    except Exception as exc:  # noqa: BLE001 — persona resolution must never break a funnel run
        print(f"  [persona] best-effort skip ({exc})")


def orchestrate(run_dir: Path, nonce: str) -> Tuple[int, Dict]:
    phases_attested: List[Dict] = []
    # FIX-COPY-02: echo the engine copy_ledger into build/fab-artifact.json (the FAB
    # scorecard the QC>=8.5 seam requires at P7). Best-effort here; P7 fails closed if
    # the file is still absent, so this can never silently skip the gate.
    _emit_fab_artifact_from_ledger(run_dir)
    gates = _phase_gates(run_dir)
    print(f"== Signature Funnel orchestrator :: run {run_dir} ==")
    _resolve_persona(run_dir)
    for order, (pid, prover, gate) in enumerate(gates):
        _mc_board_phase(run_dir, pid)  # per-phase board heartbeat (fail-soft, never a gate)
        ok, detail = gate()
        status = "pass" if ok else "fail"
        print(f"  [{status.upper():4s}] {pid:12s} ({prover}) :: {detail}")
        phases_attested.append({"id": pid, "prover": prover, "status": status,
                                "order": order, "detail": detail, "at": _now()})
        if not ok:
            print(f"ABORT: phase {pid} failed its fail-closed gate. NO certificate issued "
                  "(a later phase can never run before an earlier one passes).")
            manifest = {"run_id": run_dir.name, "aborted_at": pid, "phases": phases_attested}
            (run_dir / "process_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            return EXIT_GATE_FAIL, manifest

    # all phases passed -> mint the signed certificate
    size = None
    brief_p = run_dir / "brief.json"
    if brief_p.exists():
        try:
            size = json.loads(brief_p.read_text(encoding="utf-8")).get("funnel_size")
        except (ValueError, OSError):
            size = None
    cert = {
        "certificate": prove_sf_cert.CERT_KIND,
        "version": "1.0.0",
        "run_id": run_dir.name,
        "funnel_type": "signature_funnel",
        "funnel_size": size,
        "skill_version": (_SCRIPT_DIR / "skill-version.txt").read_text(encoding="utf-8").strip()
        if (_SCRIPT_DIR / "skill-version.txt").exists() else "1.0.0",
        "issued_at": _now(),
        "nonce_fingerprint": hashlib.sha256(nonce.encode()).hexdigest()[:16],
        "ledger_hashes": {
            "brief.json": _sha256_file(run_dir / "brief.json"),
            "copy_ledger.json": _sha256_file(run_dir / "copy_ledger.json"),
            "prompt_ledger.json": _sha256_file(run_dir / "prompt_ledger.json"),
            "media_ledger.json": _sha256_file(run_dir / "media_ledger.json"),
        },
        "phases": [{"id": p["id"], "prover": p["prover"], "status": p["status"], "order": p["order"]}
                   for p in phases_attested],
        "all_phases_pass": True,
        # A10 / T0-09 — state, on the signed certificate, whether the delegated phases
        # were backed by provider receipts. "absent" means the delegated seams attested
        # on ledger CONTENT only; the certificate can then never be read as a claim that
        # a provider was contacted. Covered by the HMAC, so it cannot be edited after.
        "delegation_receipts": _delegation_receipt_state(run_dir),
        "delivery": {"publish": "human-approval-required",
                     "preview_only": True,
                     "email_offer": "P10 optional handoff to the Email Skill project after downsell approval"},
    }
    # F4.3 — name the canonical governing persona on the signed certificate when one
    # was resolved at the brief stage (added BEFORE signing, so it is covered by the
    # HMAC; verify() does not reject extra keys).
    try:
        import persona_brief
        _pcb = persona_brief.cert_block(run_dir)
        if _pcb:
            cert["persona"] = _pcb
    except Exception:  # noqa: BLE001 — never block certification on persona surfacing
        pass
    cert["signature"] = prove_sf_cert.sign(prove_sf_cert.canonical_payload(cert), nonce)
    (run_dir / "PROCESS-CERTIFICATE.json").write_text(json.dumps(cert, indent=2), encoding="utf-8")

    code, fails = prove_sf_cert.evaluate_cert(cert, nonce)
    if code != prove_sf_cert.EXIT_OK:
        print(f"ABORT: minted certificate failed self-verification: {fails}")
        return EXIT_GATE_FAIL, cert
    print(f"CERTIFIED: all {len(gates)} phases passed in order. Signed PROCESS-CERTIFICATE.json written.")
    print("  Delivery is PREVIEW-ONLY; publishing requires explicit human approval (PRD §7 gate 7).")
    return EXIT_OK, cert


# ---------------------------------------------------------------------------
# Self-test — build a temp run-dir with the provers' own VALID fixtures, run the
# state machine end-to-end, and assert the certificate is minted + validates; then
# assert the front-door refusal and the no-skip abort.
# ---------------------------------------------------------------------------
def _full_coverage_images(size: int) -> List[Dict]:
    """Full image set covering every required (page_type, section) slot for the size
    (per prove_sf_prompt_floor.required_image_pairs), each with valid Kie+GHL provenance
    so the P9 no-pitch AND coverage asserts both pass."""
    import prove_sf_prompt_floor  # noqa: E402
    pairs = prove_sf_prompt_floor.required_image_pairs(size, prove_sf_prompt_floor.load_structure())
    images: List[Dict] = []
    for page, sec in pairs:
        section = "hero" if sec == prove_sf_prompt_floor.ANY_IMAGE else sec
        images.append({"page_type": page, "section": section,
                       "kie_task_id": f"kie_{page}_{section}",
                       "media_url": f"https://storage.gohighlevel.com/loc/x/{page}-{section}.png"})
    return images


def _write_valid_run(rd: Path, nonce: str, size: int = 3) -> None:
    import prove_sf_intake, prove_sf_copy, prove_sf_prompt_floor, prove_sf_no_pitch  # noqa: E402
    (rd / "brief.json").write_text(json.dumps(prove_sf_intake._valid_runtime(size)), encoding="utf-8")
    # FIX-XC-02a — the P0 intake gate is fail-closed on persona grounding; the run dir must
    # carry a persona-selection-log naming a registered persona slug (SOP 9.2 Step 0).
    (rd / "persona-selection-log.md").write_text(
        "# persona-selection-log\nselector_ran: true\n- selected_persona: hormozi-100m-offers\n",
        encoding="utf-8")
    (rd / "copy_ledger.json").write_text(json.dumps(prove_sf_copy._valid_ledger()), encoding="utf-8")
    # FIX-IMG-07: the prompt ledger must cover every required (page_type, section)
    # slot for this size (each prompt still clears the two-floor gate) or P2 fails-closed.
    (rd / "prompt_ledger.json").write_text(
        json.dumps(prove_sf_prompt_floor._floor_passing_full_prompts(size)), encoding="utf-8")
    # FIX-IMG-07: the media ledger must carry an image for every required
    # (page_type, section) slot for this size or P9's coverage assert fails-closed.
    media = prove_sf_no_pitch._valid_ledger()
    media["images"] = _full_coverage_images(size)
    (rd / "media_ledger.json").write_text(json.dumps(media), encoding="utf-8")
    # P5-HTML — a non-empty fragment per matrix page; P6 graph; P7 build receipt; P8 derived ledger.
    pages = prove_sf_graph.funnel_pages(size)
    (rd / "pages").mkdir(exist_ok=True)
    for profile in pages:
        (rd / "pages" / f"{profile}.fragment.html").write_text(
            f"<section data-page=\"{profile}\"><h1>{profile} fragment</h1></section>\n", encoding="utf-8")
    (rd / "funnel_graph.json").write_text(json.dumps(prove_sf_graph._valid_graph(size)), encoding="utf-8")
    (rd / "build_receipt.json").write_text(json.dumps(prove_sf_build._valid_receipt(size)), encoding="utf-8")
    (rd / "derived_pages.json").write_text(
        json.dumps(prove_sf_graph._valid_derived_ledger(size)), encoding="utf-8")
    nf = rd / ".sf_run_nonce"
    nf.write_text(nonce, encoding="utf-8")
    os.chmod(nf, 0o600)


def _stub_provider_emit(run_dir: Path, phase: str, remote_ids: List[str]) -> None:
    """Obtain delegation receipts from a PROVIDER STUB module (A10 / T0-09) instead of
    writing them here. Receipts written from this module would be stamped
    `run_signature_funnel` and refused — which is the property the self-test proves."""
    import stub_provider_adapter
    stub_provider_adapter.emit(run_dir, phase, remote_ids)


def self_test() -> int:
    ok = True
    nonce = "orch-selftest-nonce-777"
    tmp = Path(tempfile.mkdtemp(prefix="sf_orch_selftest_"))
    try:
        rd = tmp / "run-good"
        rd.mkdir()
        _write_valid_run(rd, nonce)

        # (a) front-door refusal — no nonce
        good, msg = _check_front_door(rd, None, None)
        if not good and "AF-FUN-FRONT-DOOR" in msg:
            print("SELF-TEST ok: missing nonce -> front-door refusal.")
        else:
            ok = False; print(f"SELF-TEST FAIL: missing nonce not refused: {good} {msg}")

        # (b) front-door refusal — wrong nonce
        good, msg = _check_front_door(rd, "wrong", None)
        if not good and "AF-FUN-FRONT-DOOR" in msg:
            print("SELF-TEST ok: wrong nonce -> front-door refusal.")
        else:
            ok = False; print(f"SELF-TEST FAIL: wrong nonce not refused: {good} {msg}")

        # (c) full happy path -> certified + cert validates
        good, resolved = _check_front_door(rd, nonce, None)
        if not good:
            ok = False; print(f"SELF-TEST FAIL: valid nonce refused: {resolved}")
        else:
            code, cert = orchestrate(rd, resolved)
            if code == EXIT_OK and (rd / "PROCESS-CERTIFICATE.json").exists():
                vcode, vfails = prove_sf_cert.evaluate_cert(
                    json.loads((rd / "PROCESS-CERTIFICATE.json").read_text()), nonce)
                if vcode == prove_sf_cert.EXIT_OK:
                    print("SELF-TEST ok: happy path -> signed certificate minted + validates.")
                else:
                    ok = False; print(f"SELF-TEST FAIL: minted cert invalid: {vfails}")
            else:
                ok = False; print(f"SELF-TEST FAIL: happy path did not certify (code={code}).")

        # (d) no-skip / fail-closed abort — break the copy ledger, expect NO cert
        rd2 = tmp / "run-bad"
        rd2.mkdir()
        _write_valid_run(rd2, nonce)
        import prove_sf_copy  # noqa: E402
        bad = prove_sf_copy._valid_ledger()
        bad["pages"][0]["sections"] = [s for s in bad["pages"][0]["sections"] if s.get("section") != 3]
        (rd2 / "copy_ledger.json").write_text(json.dumps(bad), encoding="utf-8")
        code, manifest = orchestrate(rd2, nonce)
        if code == EXIT_GATE_FAIL and not (rd2 / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: failing P1 gate aborts with NO certificate (fail-closed, no phase skip).")
        else:
            ok = False; print(f"SELF-TEST FAIL: bad run still certified (code={code}).")

        # (e) FIX-XC-03a — the once-no-op P5-HTML now fails closed: drop a page fragment.
        rd3 = tmp / "run-nohtml"
        rd3.mkdir()
        _write_valid_run(rd3, nonce)
        (rd3 / "pages" / "thank-you.fragment.html").unlink()
        code, _ = orchestrate(rd3, nonce)
        if code == EXIT_GATE_FAIL and not (rd3 / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: missing HTML fragment aborts at P5 with NO certificate (was a no-op).")
        else:
            ok = False; print(f"SELF-TEST FAIL: P5 no-op — run with a missing fragment still certified (code={code}).")

        # (f) FIX-XC-03a — the once-no-op P6-COMPOSE now fails closed: remove funnel_graph.json.
        rd4 = tmp / "run-nograph"
        rd4.mkdir()
        _write_valid_run(rd4, nonce)
        (rd4 / "funnel_graph.json").unlink()
        code, _ = orchestrate(rd4, nonce)
        if code == EXIT_GATE_FAIL and not (rd4 / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: missing funnel_graph aborts at P6 with NO certificate (was a no-op).")
        else:
            ok = False; print(f"SELF-TEST FAIL: P6 no-op — run with no funnel graph still certified (code={code}).")

        # (g0) FIX-IMG-07 — a partial prompt ledger (2 of N required slots) aborts at
        # P2 with AF-FUN-PROMPT-COVERAGE and NO certificate (the floor gate still clears).
        rd0 = tmp / "run-shortprompts"
        rd0.mkdir()
        _write_valid_run(rd0, nonce)
        import prove_sf_prompt_floor as _pf  # noqa: E402
        (rd0 / "prompt_ledger.json").write_text(json.dumps(_pf._valid_ledger()), encoding="utf-8")
        code, manifest0 = orchestrate(rd0, nonce)
        aborted_p2 = isinstance(manifest0, dict) and manifest0.get("aborted_at") == "P2-PROMPTS"
        if code == EXIT_GATE_FAIL and not (rd0 / "PROCESS-CERTIFICATE.json").exists() and aborted_p2:
            print("SELF-TEST ok: partial prompt ledger aborts at P2 (AF-FUN-PROMPT-COVERAGE), NO certificate.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: under-covered prompt ledger still advanced "
                  f"(code={code}, aborted_at={manifest0.get('aborted_at') if isinstance(manifest0, dict) else '?'}).")

        # (g) FIX-IMG-07 — a partial media ledger (2 of N required images) aborts at
        # P9 with AF-FUN-IMG-COVERAGE and NO certificate.
        rd5 = tmp / "run-undercovered"
        rd5.mkdir()
        _write_valid_run(rd5, nonce)
        media = json.loads((rd5 / "media_ledger.json").read_text(encoding="utf-8"))
        media["images"] = media["images"][:2]  # keep provenance valid, drop coverage
        (rd5 / "media_ledger.json").write_text(json.dumps(media), encoding="utf-8")
        code, manifest5 = orchestrate(rd5, nonce)
        aborted_p9 = isinstance(manifest5, dict) and manifest5.get("aborted_at") == "P9-CERTIFY"
        if code == EXIT_GATE_FAIL and not (rd5 / "PROCESS-CERTIFICATE.json").exists() and aborted_p9:
            print("SELF-TEST ok: partial image set aborts at P9 (AF-FUN-IMG-COVERAGE), NO certificate.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: under-covered media ledger still certified "
                  f"(code={code}, aborted_at={manifest5.get('aborted_at') if isinstance(manifest5, dict) else '?'}).")
        # (g) FIX-COPY-02 — the happy path emitted the FAB scorecard from the copy ledger.
        if (rd / "build" / "fab-artifact.json").exists():
            print("SELF-TEST ok: happy path emitted build/fab-artifact.json (copy ledger echoed).")
        else:
            ok = False; print("SELF-TEST FAIL: happy path did not emit the FAB scorecard file.")

        # (h) FIX-COPY-02 — P7 now REQUIRES the FAB scorecard FILE: a valid build receipt
        # with NO fab-artifact must fail closed at AF-FUN-BUILD-FAB (was a silent skip).
        rd5 = tmp / "run-nofab"
        rd5.mkdir()
        (rd5 / "build").mkdir()
        (rd5 / "build_receipt.json").write_text(
            json.dumps(prove_sf_build._valid_receipt(3)), encoding="utf-8")
        g_ok, g_detail = _gate_build(rd5)
        if not g_ok and "AF-FUN-BUILD-FAB" in g_detail:
            print("SELF-TEST ok: P7 fails closed with AF-FUN-BUILD-FAB when the FAB scorecard is absent.")
        else:
            ok = False; print(f"SELF-TEST FAIL: P7 accepted a build with no FAB scorecard: {g_ok} {g_detail}")

        # (i) FIX-COPY-02 — a FAB artifact that echoes NO copy is an un-provable (thin) build.
        (rd5 / "build" / "fab-artifact.json").write_text(
            json.dumps({"kind": "funnel", "pages": [{"name": "main", "copy": {}}]}),
            encoding="utf-8")
        g_ok, g_detail = _gate_build(rd5)
        if not g_ok and "AF-FUN-BUILD-FAB" in g_detail:
            print("SELF-TEST ok: P7 fails closed when the FAB scorecard echoes no copy.")
        else:
            ok = False; print(f"SELF-TEST FAIL: P7 accepted an empty-copy FAB scorecard: {g_ok} {g_detail}")

        # -------------------------------------------------------------------
        # A10 / T0-09 + T0-11 — the certification seams.
        # -------------------------------------------------------------------
        # (j) P3-IMAGES no longer attests on file existence: a ledger the run wrote
        #     with NO provider task ids is not a delegated image generation.
        rdj = tmp / "run-noprovenance"
        rdj.mkdir()
        _write_valid_run(rdj, nonce)
        led = json.loads((rdj / "media_ledger.json").read_text(encoding="utf-8"))
        for im in led["images"]:
            im["kie_task_id"] = ""
        (rdj / "media_ledger.json").write_text(json.dumps(led), encoding="utf-8")
        g_ok, g_detail = _gate_p3_images(rdj)
        if not g_ok and "AF-FUN-DELEG-IMAGES" in g_detail:
            print("SELF-TEST ok: P3-IMAGES fails closed on a ledger with no provider task ids "
                  "(file existence is no longer proof of delegation).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: P3-IMAGES attested a ledger with no provenance: {g_ok} {g_detail}")

        # (k) P4-MEDIA no longer attests on file existence: an off-host URL is not an upload.
        rdk = tmp / "run-offhost"
        rdk.mkdir()
        _write_valid_run(rdk, nonce)
        led = json.loads((rdk / "media_ledger.json").read_text(encoding="utf-8"))
        led["images"][0]["media_url"] = "https://cdn.somewhere-else.test/hero.png"
        (rdk / "media_ledger.json").write_text(json.dumps(led), encoding="utf-8")
        g_ok, g_detail = _gate_p4_media(rdk)
        if not g_ok and "AF-FUN-DELEG-MEDIA" in g_detail:
            print("SELF-TEST ok: P4-MEDIA fails closed on an off-host media URL.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: P4-MEDIA attested an off-host media URL: {g_ok} {g_detail}")

        # (l) SELF-AUTHORED RECEIPT — the run stamps its own provider receipt. The
        #     subject of a certificate may not author the evidence it is judged on,
        #     so the seam must REFUSE it (and must not be more permissive than the
        #     absent case, which is the whole shape of the A10 defect).
        rdl = tmp / "run-selfauthored-receipt"
        rdl.mkdir()
        _write_valid_run(rdl, nonce)
        import delegation_receipt as _dr  # noqa: E402
        led = json.loads((rdl / "media_ledger.json").read_text(encoding="utf-8"))
        for im in led["images"]:
            # written from THIS module -> recorded_by == run_signature_funnel
            _dr.record(rdl, phase="P3-IMAGES", provider="kie", operation="createTask",
                       provider_response_id="kie-resp-selfauthored", http_status=200,
                       remote_id=_image_key(im), covers=[_image_key(im)])
        g_ok, g_detail = _gate_p3_images(rdl)
        if not g_ok and "SELF-AUTHORED" in g_detail:
            print("SELF-TEST ok: a receipt the ORCHESTRATOR wrote for itself is refused "
                  "(AF-FUN-DELEG-RECEIPT-SELF-AUTHORED).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: the run certified on a receipt it authored itself: "
                  f"{g_ok} {g_detail}")

        # (m) A STUB PROVIDER's receipt — evidence from a module that is not the run
        #     under test — is accepted, and the certificate records it as present.
        rdm = tmp / "run-stub-receipt"
        rdm.mkdir()
        _write_valid_run(rdm, nonce)
        led = json.loads((rdm / "media_ledger.json").read_text(encoding="utf-8"))
        _stub_provider_emit(rdm, "P3-IMAGES", [_image_key(i) for i in led["images"]])
        _stub_provider_emit(rdm, "P4-MEDIA", [_image_key(i) for i in led["images"]])
        g_ok, g_detail = _gate_p3_images(rdm)
        g_ok4, g_detail4 = _gate_p4_media(rdm)
        if g_ok and g_ok4 and "receipts verified" in g_detail and "receipts verified" in g_detail4:
            print("SELF-TEST ok: provider-stub receipts verify at P3 and P4 "
                  "(fixture produced by a stub, never by the run under test).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: stub-provider receipts not verified: "
                  f"P3={g_ok}/{g_detail} P4={g_ok4}/{g_detail4}")
        if _delegation_receipt_state(rdm) == "present" and _delegation_receipt_state(rd) == "absent":
            print("SELF-TEST ok: the certificate records delegation_receipts present/absent "
                  "(a certificate cannot imply provider evidence it does not carry).")
        else:
            ok = False
            print("SELF-TEST FAIL: delegation_receipts certificate state is wrong "
                  f"(stub={_delegation_receipt_state(rdm)}, plain={_delegation_receipt_state(rd)}).")

        # (n) A receipt that covers only SOME of the ledger's rows does not attest the
        #     rest — omission inside a receipt store is still omission.
        rdn = tmp / "run-partial-receipt"
        rdn.mkdir()
        _write_valid_run(rdn, nonce)
        led = json.loads((rdn / "media_ledger.json").read_text(encoding="utf-8"))
        _stub_provider_emit(rdn, "P3-IMAGES", [_image_key(led["images"][0])])
        g_ok, g_detail = _gate_p3_images(rdn)
        if not g_ok and "COVERAGE" in g_detail:
            print("SELF-TEST ok: a receipt covering 1 of N ledger rows fails coverage.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: partial receipt coverage attested: {g_ok} {g_detail}")

        # (o) T0-11 — a 7-step funnel whose build receipt supplies 3 pages must abort at
        #     P7 with AF-FUN-BUILD-PAGESET and mint NO certificate. This is the exact
        #     shape the finding proved returned zero violations.
        rdo = tmp / "run-undersized-build"
        rdo.mkdir()
        _write_valid_run(rdo, nonce, size=7)
        rcpt = json.loads((rdo / "build_receipt.json").read_text(encoding="utf-8"))
        rcpt["pages"] = [p for p in rcpt["pages"]
                         if p.get("page_type") in ("main", "upsell", "thank-you")]
        (rdo / "build_receipt.json").write_text(json.dumps(rcpt), encoding="utf-8")
        code, manifesto = orchestrate(rdo, nonce)
        aborted_p7 = isinstance(manifesto, dict) and manifesto.get("aborted_at") == "P7-BUILD"
        if code == EXIT_GATE_FAIL and not (rdo / "PROCESS-CERTIFICATE.json").exists() and aborted_p7:
            print("SELF-TEST ok: a 7-step funnel with a 3-page build receipt aborts at P7 "
                  "(AF-FUN-BUILD-PAGESET), NO certificate.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: incomplete funnel build still certified (code={code}, "
                  f"aborted_at={manifesto.get('aborted_at') if isinstance(manifesto, dict) else '?'}).")

        print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
        return 0 if ok else 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Command Center board card (FAIL-SOFT). Mirrors Skill-48 (ad_director) and the
# presentations build_deck._board_patch_phase pattern via the shared mc_board
# helper: land ONE mc-route card per run and advance it. A disabled board
# (no COMMAND_CENTER_URL) is a clean no-op; ANY failure is swallowed — the board
# is a VIEW, never a gate, and can never affect this orchestrator's exit code.
# ---------------------------------------------------------------------------
def _mc_board_begin(run_dir: Path) -> Optional[str]:
    try:
        import mc_board
        return mc_board.begin_run(
            run_dir, slug=run_dir.name,
            title=f"Signature Funnel — {run_dir.name}",
            # FIX-BOARD-DEPT-01: route the CC card to Skill 49's real owning
            # department. "funnels" was NEVER a seeded fleet department (absent
            # from 23-ai-workforce-blueprint/department-naming-map.json + the
            # department-floor), so every card silently misrouted/dropped. Skill
            # 49's authoritative department in skill-department-map.json is
            # web-development (primary role: signature-funnel-specialist).
            department="web-development", persona="Signature Funnel",
            source="signature-funnel")
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        print(f"[mc_board] begin best-effort skip ({exc})", file=sys.stderr)
        return None


def _mc_board_phase(run_dir: Path, phase_id: str) -> None:
    """Per-phase board heartbeat: advance this run's card to (phase_id, in_progress).
    FAIL-SOFT — the board is a VIEW, never a gate; any failure is swallowed."""
    try:
        import mc_board
        mc_board.card_advance(run_dir, phase_id=phase_id, status="in_progress",
                              note=f"phase {phase_id} running")
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        print(f"[mc_board] phase {phase_id} best-effort skip ({exc})", file=sys.stderr)


def _mc_deliverable_url(run_dir: Path) -> str:
    """Best-effort deliverable link to register on the card: the first http(s) URL
    found in the run's media ledger. Empty string when none — never raises."""
    try:
        led = run_dir / "media_ledger.json"
        if led.exists():
            import re
            m = re.search(r"https?://[^\s\"']+", led.read_text(encoding="utf-8"))
            if m:
                return m.group(0)
    except Exception:  # noqa: BLE001 — deliverable link is best-effort only.
        pass
    return ""


def _mc_board_done(run_dir: Path, task_id: Optional[str]) -> None:
    """Terminal producer move: card -> REVIEW (never done). review->done is owned by
    the independent QC scorer. The deliverable link is registered on the card."""
    try:
        import mc_board
        mc_board.complete_run(run_dir, task_id,
                              note="certified — awaiting QC promotion",
                              deliverable_url=_mc_deliverable_url(run_dir))
    except Exception as exc:  # noqa: BLE001
        print(f"[mc_board] done best-effort skip ({exc})", file=sys.stderr)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic no-skip Signature Funnel orchestrator. Requires the "
                    "front-door nonce; emits a signed PROCESS-CERTIFICATE only on all-phases-pass.")
    ap.add_argument("--run-dir", help="the run directory (brief/copy/prompt/media ledgers)")
    ap.add_argument("--nonce", help="the run-scoped front-door nonce (or SF_RUN_NONCE)")
    ap.add_argument("--nonce-file", help="path to the nonce file (default <run-dir>/.sf_run_nonce)")
    ap.add_argument("--self-test", action="store_true", help="run the built-in end-to-end fixtures")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.run_dir:
        print("USAGE ERROR: pass --run-dir <dir> (or --self-test).")
        return EXIT_FRONT_DOOR
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"USAGE ERROR: run-dir {run_dir} is not a directory.")
        return EXIT_FRONT_DOOR

    nonce_file = Path(args.nonce_file).expanduser() if args.nonce_file else None
    good, resolved = _check_front_door(run_dir, args.nonce, nonce_file)
    if not good:
        print(resolved)
        return EXIT_FRONT_DOOR

    _mc_task = _mc_board_begin(run_dir)
    code, _ = orchestrate(run_dir, resolved)
    if code == EXIT_OK:
        _mc_board_done(run_dir, _mc_task)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
