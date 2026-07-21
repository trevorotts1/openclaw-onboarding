#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_sales_page_assets.py — the deterministic Sales Page Assets orchestrator (Skill 56).

A no-skip state machine. It runs the fixed phase spine P0..P9 IN ORDER, shells each phase's
fail-closed prover(s), and — only when EVERY phase passes — emits a signed
PROCESS-CERTIFICATE.json. A failing gate aborts the run (fail-closed) and NO certificate is
written, so an incomplete or non-compliant asset stack can never reach Complete.

FRONT-DOOR NONCE (required): the canonical entry shell (sales-page-assets-entry.sh) writes a
run-scoped 0600 nonce file and passes its value with --nonce. The orchestrator refuses to run
unless the supplied nonce matches the file — a direct `python3 run_sales_page_assets.py`
without the front-door nonce dies with AF-SP56-FRONT-DOOR. The same nonce keys the certificate
HMAC, so a certificate can only be minted by a real front-door run.

DELEGATION SEAMS (never forked here): image generation is delegated to Skill 47 (kie_image.py)
or the client's own image provider; GHL media folder + upload and the funnel/page build are
delegated to Skill 6 (ghl_media.py / ghl_rest_canvas.py); the bump copy routes to the Skill 44
seam. CLIENT runtime uses the client's OWN providers, never Anthropic.

Run-dir inputs:
  brief.json            — locked intake brief         (P0 gate: prove_sp_intake.py)
  image_plan.json       — image prompts + slice map   (P1 gate: prove_sp_image_plan.py)
  media_ledger.json     — image records + GHL media    (P2/P4 delegation artifact)
  copy_ledger.json      — the 7 copy assets            (P3 gate: 4 copy provers)
  funnel-manifest.json  — the Track-2 build bundle     (P7 gate: prove_sp_bundle.py)

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
import prove_sp_cert  # noqa: E402  (shared cert schema + HMAC signing; guarantees agreement)

EXIT_OK = 0
EXIT_GATE_FAIL = 2
EXIT_FRONT_DOOR = 3

PY = sys.executable or "python3"

# The four copy provers that make up the P3-COPY suite (all run against copy_ledger.json).
COPY_SUITE = (
    "prove_sp_main_structure.py",
    "prove_sp_upsell_structure.py",
    "prove_sp_highticket_band.py",
    "prove_sp_bump_band.py",
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _shell_prover(script: str, args: List[str]) -> Tuple[bool, str]:
    path = _SCRIPTS / script
    if not path.exists():
        return False, f"prover {script} not found at {path}"
    proc = subprocess.run([PY, str(path), *args], capture_output=True, text=True)
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    detail = tail[-1] if tail else f"rc={proc.returncode}"
    return proc.returncode == 0, f"{script} rc={proc.returncode} :: {detail}"


def _copy_suite(run_dir: Path) -> Tuple[bool, str]:
    ledger = str(run_dir / "copy_ledger.json")
    details = []
    all_ok = True
    for script in COPY_SUITE:
        ok, detail = _shell_prover(script, ["--ledger", ledger])
        all_ok = all_ok and ok
        details.append(detail)
    return all_ok, " | ".join(details)


def _image_plan_suite(run_dir: Path) -> Tuple[bool, str]:
    """P1 runs BOTH image-plan provers: slice COVERAGE (prove_sp_image_plan) AND prompt
    STRENGTH (prove_sp_prompt_floor, FIX-XC-04e) — a weak prompt can never reach a paid call."""
    plan = str(run_dir / "image_plan.json")
    details, all_ok = [], True
    for script, args in (("prove_sp_image_plan.py", ["--plan", plan]),
                         ("prove_sp_prompt_floor.py", ["--ledger", plan])):
        ok, detail = _shell_prover(script, args)
        all_ok = all_ok and ok
        details.append(detail)
    return all_ok, " | ".join(details)


def _media_gate(run_dir: Path) -> Tuple[bool, str]:
    """P4-MEDIA — artifact-backed provenance + coverage (FIX-IMG-02). The media ledger content
    is validated, not merely present: prove_sp_media.py fails closed unless every media record
    carries a real image-provider taskId + a GHL media host, and every image_plan.json stage is
    covered by >= 1 media record. A blank/off-host/placeholder image can no longer certify."""
    return _shell_prover("prove_sp_media.py",
                         ["--media", str(run_dir / "media_ledger.json"),
                          "--plan", str(run_dir / "image_plan.json")])


def _load_run_json(run_dir: Path, name: str) -> Tuple[Optional[Dict], str]:
    p = run_dir / name
    if not p.is_file():
        return None, f"{name} absent"
    try:
        return json.loads(p.read_text(encoding="utf-8")), ""
    except (ValueError, OSError) as exc:
        return None, f"cannot parse {name} ({exc})"


def _fragments_gate(run_dir: Path) -> Tuple[bool, str]:
    """P5 — artifact-backed (FIX-XC-03b): every PAGE step in the funnel-manifest must have a
    non-empty fragment file on disk. Fragments are the deterministic sanitize/fragment-ize
    output (Skill 6); a missing/empty fragment fails CLOSED."""
    data, err = _load_run_json(run_dir, "funnel-manifest.json")
    if data is None:
        return False, f"AF-SP56-FRAGMENT-MISSING: {err} (cannot verify P5 fragments)"
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return False, "AF-SP56-FRAGMENT-MISSING: funnel-manifest carries no steps"
    page_steps = [s for s in steps if isinstance(s, dict)
                  and str(s.get("stage", "")).strip().lower() != "bump"
                  and isinstance(s.get("fragment_path"), str) and s["fragment_path"].strip()]
    if not page_steps:
        return False, "AF-SP56-FRAGMENT-MISSING: no page step declares a fragment_path"
    missing = []
    for s in page_steps:
        fp = run_dir / s["fragment_path"]
        if not fp.is_file() or not fp.read_text(encoding="utf-8", errors="ignore").strip():
            missing.append(s["fragment_path"])
    if missing:
        return False, (f"AF-SP56-FRAGMENT-MISSING: {len(missing)} fragment file(s) absent/empty "
                       f"(e.g. {missing[:3]})")
    return True, f"P5 fragments present + non-empty for all {len(page_steps)} page step(s)"


# ---------------------------------------------------------------------------
# A10 / T0-10 — the delivery, document and build seams.
#
# THE DEFECT: the documents phase required only a non-empty list of entries with no
# document identifier; the delivery phase required only a non-empty subject and a
# non-empty folder link with no send receipt; the build phase required only a
# non-empty preview-URL list and a bare number read out of the same file. The
# shipped artifact writer then fabricated all three IN-PROCESS with example-domain
# URLs and a hardcoded 8.7, and the self-test minted and validated a signed
# certificate from exactly that fixture. The certificate asserted that client Docs
# were created, a folder link was emailed and a page build completed — with no
# evidence beyond strings the run wrote.
#
# THIS RELEASE (writer-before-requirer sequencing):
#   * a caller-authored PLACEHOLDER can no longer stand in for a real resource: every
#     doc, folder and preview link must be an http(s) URL on a non-placeholder host.
#     A genuine Drive/GHL URL always satisfies this, so no run that could certify
#     before can fail now.
#   * any provider receipt that IS present must hold strictly, and the certificate
#     RECORDS whether receipts were present — so it can never be read as a claim that
#     a document API, a mail send or a remote build was actually contacted.
#   * the self-test fixture now comes from a PROVIDER STUB, not from the run.
# NEXT: delegation_receipt.require() replaces validate_if_present() — a document id,
# a send-receipt id and a remote build id become mandatory — once the delegated
# skills emit receipts on every path.
# ---------------------------------------------------------------------------
PLACEHOLDER_HOSTS = (
    "example.com", "example.org", "example.net", "example.edu", "invalid",
    "localhost", "127.0.0.1", "0.0.0.0", "test.com", "changeme.com", "todo.com",
)


def _url_host(url: Any) -> str:
    from urllib.parse import urlparse
    if not isinstance(url, str):
        return ""
    try:
        return (urlparse(url.strip()).hostname or "").lower()
    except (ValueError, TypeError):
        return ""


def _real_url(url: Any) -> Tuple[bool, str]:
    """(ok, reason). An http(s) URL whose host is not a placeholder host or a
    subdomain of one. Matched on the parsed HOST, so a genuine vendor domain that
    merely contains one of these words is never false-failed."""
    if not isinstance(url, str) or not url.strip().lower().startswith(("http://", "https://")):
        return False, f"{url!r} is not an http(s) URL"
    host = _url_host(url)
    if not host:
        return False, f"{url!r} has no host"
    if any(host == ph or host.endswith("." + ph) for ph in PLACEHOLDER_HOSTS):
        return False, f"{url!r} resolves to placeholder host {host!r}"
    return True, host


def _receipt_seam(run_dir: Path, phase: str, keys: List[str],
                  content_detail: str) -> Tuple[bool, str]:
    try:
        import delegation_receipt
    except ImportError as exc:  # noqa: BLE001 — a missing contract module is fail-closed
        return False, (f"AF-SP56-DELEG-RECEIPT: delegation_receipt.py is not importable "
                       f"({exc}) — the delegated seam {phase} cannot be attested")
    ok, detail, state = delegation_receipt.validate_if_present(
        run_dir, phase, must_cover=keys or None, af="AF-SP56-DELEG-RECEIPT")
    if not ok:
        return False, detail
    return True, f"{content_detail} :: receipts {state} ({detail})"


def _delegation_receipt_state(run_dir: Path) -> str:
    try:
        import delegation_receipt
        return delegation_receipt.store_state(run_dir)
    except Exception:  # noqa: BLE001 — a certificate field must never break certification
        return "unknown"


def _docs_gate(run_dir: Path) -> Tuple[bool, str]:
    """P6 — the Track-1 client Docs manifest must exist and name at least one
    client-editable Doc, each reachable at a real (non-placeholder) URL."""
    data, err = _load_run_json(run_dir, "drive_docs.json")
    if data is None:
        return False, f"AF-SP56-DOCS-MISSING: {err} (Track-1 client Docs artifact)"
    docs = data.get("docs")
    entries = [d for d in docs if isinstance(d, dict)] if isinstance(docs, list) else []
    if not entries:
        return False, "AF-SP56-DOCS-MISSING: drive_docs.json carries no docs entries"
    bad, keys = [], []
    for i, d in enumerate(entries):
        who = str(d.get("label") or d.get("name") or f"#{i}")
        url = d.get("url") or d.get("doc_url") or d.get("link")
        good, reason = _real_url(url)
        if not good:
            bad.append(f"{who}: {reason}")
        keys.append(str(d.get("doc_id") or d.get("id") or d.get("file_id") or url or who))
    if bad:
        return False, (f"AF-SP56-DOCS-PLACEHOLDER: {len(bad)} doc entr(ies) have no real "
                       f"document URL (e.g. {bad[:2]}) — a caller-authored placeholder is "
                       "not a created client Doc")
    return _receipt_seam(run_dir, "P6-DOCS", keys,
                         f"P6 Track-1 Docs manifest present ({len(entries)} doc(s), real URLs)")


def _deliver_gate(run_dir: Path) -> Tuple[bool, str]:
    """P8 — the delivery record must exist with a productionized (non-test) subject
    and a real (non-placeholder) folder link."""
    data, err = _load_run_json(run_dir, "delivery.json")
    if data is None:
        return False, f"AF-SP56-DELIVER-MISSING: {err}"
    subject = str(data.get("subject", "")).strip()
    if not subject:
        return False, "AF-SP56-DELIVER-MISSING: delivery.json has no subject"
    if "test" in subject.lower():
        return False, f"AF-SP56-DELIVER-SUBJECT: leftover test subject {subject!r} (productionize it)"
    link = data.get("folder_link", "")
    if not str(link).strip():
        return False, "AF-SP56-DELIVER-MISSING: delivery.json has no folder_link"
    good, reason = _real_url(link)
    if not good:
        return False, (f"AF-SP56-DELIVER-PLACEHOLDER: folder_link {reason} — a caller-authored "
                       "placeholder link was not delivered to anybody")
    keys = [str(data.get("send_receipt_id") or data.get("message_id") or link)]
    return _receipt_seam(run_dir, "P8-DELIVER", keys,
                         "P8 delivery artifact present (subject productionized, real folder link)")


def _build_receipt_gate(run_dir: Path) -> Tuple[bool, str]:
    """P9 — a Skill 6 build receipt must exist with real (non-placeholder) preview
    URLs and a build QC score >= 8.5 (in addition to the funnel-manifest)."""
    if not (run_dir / "funnel-manifest.json").is_file():
        return False, "AF-SP56-BUILD-RECEIPT: funnel-manifest.json absent (no build to hand off)"
    data, err = _load_run_json(run_dir, "build_receipt.json")
    if data is None:
        return False, f"AF-SP56-BUILD-RECEIPT: {err} (Skill 6 build handoff receipt)"
    urls = data.get("preview_urls")
    if not (isinstance(urls, list) and [u for u in urls if str(u).strip()]):
        return False, "AF-SP56-BUILD-RECEIPT: build_receipt.json carries no non-empty preview_urls"
    bad = []
    for u in urls:
        good, reason = _real_url(u)
        if not good:
            bad.append(reason)
    if bad:
        return False, (f"AF-SP56-BUILD-PLACEHOLDER: {len(bad)} preview URL(s) are not real "
                       f"(e.g. {bad[:2]}) — a caller-authored preview proves no page was built")
    try:
        score = float(data.get("qc_score"))
    except (TypeError, ValueError):
        return False, "AF-SP56-BUILD-RECEIPT: build_receipt.json qc_score missing/non-numeric"
    if score < 8.5:
        return False, f"AF-SP56-BUILD-RECEIPT: build QC {score} < 8.5 (fail-closed)"
    keys = [str(data.get("remote_build_id") or data.get("funnel_id") or u) for u in urls]
    return _receipt_seam(run_dir, "P9-HANDOFF", keys,
                         f"P9 build receipt present (QC {score}, {len(urls)} real preview url(s))")


def _images_gate(run_dir: Path) -> Tuple[bool, str]:
    """P2-IMAGES — A10 / T0-09. The phase used to attest the moment media_ledger.json
    EXISTED, and the run writes that file. It now requires the ledger to carry image
    records with a real image-provider task id. The full provenance + per-stage
    coverage check still runs at P4 (prove_sp_media.py); this only stops the phase
    that CLAIMS image generation from being satisfied by an empty file."""
    data, err = _load_run_json(run_dir, "media_ledger.json")
    if data is None:
        return False, (f"AF-SP56-IMAGES-MISSING: {err} — Skill 47 kie_image.py (or the "
                       "client's own image provider) produced nothing")
    imgs = data.get("images")
    records = [i for i in imgs if isinstance(i, dict)] if isinstance(imgs, list) else []
    if not records:
        return False, ("AF-SP56-IMAGES-MISSING: media_ledger.json carries no image records — "
                       "an empty ledger is not a delegated image generation")
    bad, keys = [], []
    for i, img in enumerate(records):
        tid = img.get("task_id", img.get("kie_task_id"))
        norm = str(tid).strip().lower() if tid is not None else ""
        if tid is None or norm in ("", "native", "placeholder", "none", "null", "n/a", "tbd", "todo"):
            bad.append(f"{img.get('asset_key', f'#{i}')}={tid!r}")
        keys.append(str(tid or img.get("asset_key") or f"#{i}"))
    if bad:
        return False, (f"AF-SP56-IMAGES-PROVENANCE: {len(bad)} image record(s) carry no real "
                       f"image-provider task id (e.g. {bad[:3]})")
    return _receipt_seam(run_dir, "P2-IMAGES", keys,
                         f"delegated: Skill 47 kie_image.py OR the client's own image provider "
                         f"({len(records)} record(s) with a provider task id)")


def _delegation_seam(run_dir: Path, required_file: Optional[str], label: str) -> Tuple[bool, str]:
    """Retained for seams with no content contract. A10 / T0-09: the image seam no
    longer uses it — file existence is not proof that a provider ran."""
    if required_file is not None:
        p = run_dir / required_file
        if not p.exists():
            return False, f"delegated artifact {required_file} absent (expected for: {label})"
    return True, f"delegated: {label}"


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Phase spine — ids + order MUST match prove_sp_cert.EXPECTED_PHASES.
def _phase_gates(run_dir: Path) -> List[Tuple[str, str, Callable[[], Tuple[bool, str]]]]:
    return [
        ("P0-INTAKE", "prove_sp_intake.py",
         lambda: _shell_prover("prove_sp_intake.py", [str(run_dir / "brief.json")])),
        ("P1-IMAGE-PLAN", "prove_sp_image_plan.py + prove_sp_prompt_floor.py",
         lambda: _image_plan_suite(run_dir)),
        ("P2-IMAGES", "kie_image.py",
         lambda: _images_gate(run_dir)),
        ("P3-COPY", "prove_sp_copy_suite",
         lambda: _copy_suite(run_dir)),
        ("P4-MEDIA", "ghl_media.py + prove_sp_media.py",
         lambda: _media_gate(run_dir)),
        ("P5-FRAGMENTS", "fragment_strip",
         lambda: _fragments_gate(run_dir)),
        ("P6-DOCS", "drive_docs",
         lambda: _docs_gate(run_dir)),
        ("P7-BUNDLE", "prove_sp_bundle.py",
         lambda: _shell_prover("prove_sp_bundle.py", ["--manifest", str(run_dir / "funnel-manifest.json")])),
        ("P8-DELIVER", "delivery_email",
         lambda: _deliver_gate(run_dir)),
        ("P9-HANDOFF", "ghl_rest_canvas.py",
         lambda: _build_receipt_gate(run_dir)),
    ]


def _check_front_door(run_dir: Path, nonce: Optional[str], nonce_file: Optional[Path]) -> Tuple[bool, str]:
    nf = nonce_file or (run_dir / ".spa_run_nonce")
    if not nf.exists():
        return False, f"AF-SP56-FRONT-DOOR: no run-scoped nonce file at {nf} — run must start via sales-page-assets-entry.sh"
    supplied = nonce if nonce is not None else os.environ.get("SPA_RUN_NONCE")
    if not supplied:
        return False, "AF-SP56-FRONT-DOOR: no --nonce / SPA_RUN_NONCE supplied (front-door nonce required)"
    on_disk = nf.read_text(encoding="utf-8").strip()
    if not on_disk or supplied.strip() != on_disk:
        return False, "AF-SP56-FRONT-DOOR: supplied nonce does not match the run-scoped nonce file"
    return True, supplied.strip()


def _resolve_persona(run_dir: Path) -> None:
    """F4.3 — resolve the sales page's canonical governing persona at the brief
    stage (best-effort; never blocks the run). Writes persona-selection.json for the
    copy prompts and the certificate. A bare box / unreachable selector is a clean skip."""
    try:
        sys.path.insert(0, str(_SCRIPTS))
        import persona_brief
        sel = persona_brief.resolve(run_dir)
        if sel:
            print(f"  [persona] {sel.get('persona_id')} ({sel.get('persona_name')}) "
                  f"via {sel.get('source')}")
    except Exception as exc:  # noqa: BLE001 — persona resolution must never break a run
        print(f"  [persona] best-effort skip ({exc})")


def orchestrate(run_dir: Path, nonce: str) -> Tuple[int, Dict]:
    phases_attested: List[Dict] = []
    gates = _phase_gates(run_dir)
    print(f"== Sales Page Assets orchestrator :: run {run_dir} ==")
    _resolve_persona(run_dir)
    for order, (pid, prover, gate) in enumerate(gates):
        _mc_board_phase(run_dir, pid)  # per-phase board heartbeat (fail-soft, never a gate)
        ok, detail = gate()
        status = "pass" if ok else "fail"
        print(f"  [{status.upper():4s}] {pid:14s} ({prover}) :: {detail}")
        phases_attested.append({"id": pid, "prover": prover, "status": status,
                                "order": order, "detail": detail, "at": _now()})
        if not ok:
            print(f"ABORT: phase {pid} failed its fail-closed gate. NO certificate issued "
                  "(a later phase can never run before an earlier one passes).")
            manifest = {"run_id": run_dir.name, "aborted_at": pid, "phases": phases_attested}
            (run_dir / "process_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            return EXIT_GATE_FAIL, manifest

    cert = {
        "certificate": prove_sp_cert.CERT_KIND,
        "version": "1.0.0",
        "run_id": run_dir.name,
        "funnel_type": "sales_page_assets",
        "skill_version": (_SCRIPT_DIR / "skill-version.txt").read_text(encoding="utf-8").strip()
        if (_SCRIPT_DIR / "skill-version.txt").exists() else "1.0.0",
        "issued_at": _now(),
        "nonce_fingerprint": hashlib.sha256(nonce.encode()).hexdigest()[:16],
        "ledger_hashes": {
            "brief.json": _sha256_file(run_dir / "brief.json"),
            "image_plan.json": _sha256_file(run_dir / "image_plan.json"),
            "copy_ledger.json": _sha256_file(run_dir / "copy_ledger.json"),
            "media_ledger.json": _sha256_file(run_dir / "media_ledger.json"),
            "funnel-manifest.json": _sha256_file(run_dir / "funnel-manifest.json"),
        },
        "phases": [{"id": p["id"], "prover": p["prover"], "status": p["status"], "order": p["order"]}
                   for p in phases_attested],
        "all_phases_pass": True,
        # A10 / T0-09, T0-10 — state, on the signed certificate, whether the delegated
        # phases were backed by provider receipts. "absent" means they attested on
        # artifact CONTENT only, so the certificate can never be read as a claim that a
        # provider, a document API or a mail send was contacted. Covered by the HMAC.
        "delegation_receipts": _delegation_receipt_state(run_dir),
        "delivery": {"publish": "human-approval-required",
                     "preview_only": True,
                     "two_track": "Track 1 client Docs (editable) + Track 2 build bundle (Skill 6)",
                     "bump_seam": "Skill 44 order-bump widget (P4->P5 board handoff)"},
    }
    # F4.3 — name the canonical governing persona on the signed certificate when one
    # was resolved at the brief stage (added BEFORE signing; verify() tolerates extra keys).
    try:
        import persona_brief
        _pcb = persona_brief.cert_block(run_dir)
        if _pcb:
            cert["persona"] = _pcb
    except Exception:  # noqa: BLE001 — never block certification on persona surfacing
        pass
    cert["signature"] = prove_sp_cert.sign(prove_sp_cert.canonical_payload(cert), nonce)
    (run_dir / "PROCESS-CERTIFICATE.json").write_text(json.dumps(cert, indent=2), encoding="utf-8")

    code, fails = prove_sp_cert.evaluate_cert(cert, nonce)
    if code != prove_sp_cert.EXIT_OK:
        print(f"ABORT: minted certificate failed self-verification: {fails}")
        return EXIT_GATE_FAIL, cert
    print(f"CERTIFIED: all {len(gates)} phases passed in order. Signed PROCESS-CERTIFICATE.json written.")
    print("  Delivery is PREVIEW-ONLY; publishing requires explicit human approval (Skill 6 gate).")
    return EXIT_OK, cert


# ---------------------------------------------------------------------------
# Self-test — build a temp run-dir with the provers' own VALID fixtures, run the state
# machine end-to-end, and assert the certificate is minted + validates; then assert the
# front-door refusal and the no-skip abort.
# ---------------------------------------------------------------------------
def _write_valid_run(rd: Path, nonce: str, *, with_receipts: bool = True) -> None:
    import prove_sp_intake, prove_sp_prompt_floor, prove_sp_bundle  # noqa: E402
    import prove_sp_main_structure, prove_sp_upsell_structure  # noqa: E402
    import prove_sp_highticket_band, prove_sp_bump_band  # noqa: E402

    (rd / "brief.json").write_text(json.dumps(prove_sp_intake._valid_runtime()), encoding="utf-8")
    # FIX-XC-02a — the P0 intake gate is fail-closed on persona grounding; the run dir must
    # carry a persona-selection-log naming a registered persona slug (SOP-SALESPAGE-01 §3).
    (rd / "persona-selection-log.md").write_text(
        "# persona-selection-log\nselector_ran: true\n- selected_persona: hormozi-100m-offers\n",
        encoding="utf-8")
    # floor-compliant, slice-complete image plan (clears BOTH P1 provers).
    (rd / "image_plan.json").write_text(json.dumps(prove_sp_prompt_floor._valid_plan(12)), encoding="utf-8")

    # merged copy ledger with all 7 assets (main a/b, upsell a/b, downsell, high-ticket, bump)
    copy_assets = []
    copy_assets += prove_sp_main_structure._valid_ledger()["assets"]
    copy_assets += prove_sp_upsell_structure._valid_ledger()["assets"]
    copy_assets += prove_sp_highticket_band._valid_ledger()["assets"]
    copy_assets += prove_sp_bump_band._valid_ledger()["assets"]
    (rd / "copy_ledger.json").write_text(json.dumps({"assets": copy_assets}), encoding="utf-8")

    # media ledger MUST cover every image_plan stage (FIX-IMG-02 P4-MEDIA provenance+coverage):
    # one GHL-host, real-taskId record per distinct plan stage.
    plan = json.loads((rd / "image_plan.json").read_text(encoding="utf-8"))
    plan_stages = []
    for pr in plan.get("prompts", []):
        st = str(pr.get("stage", "")).strip().lower()
        if st and st not in plan_stages:
            plan_stages.append(st)
    media_images = [
        {"asset_key": f"jane-doe__glow-method__{st}__img-{i:02d}__v01", "stage": st,
         "task_id": f"kie-{i:02d}", "ghl_media_url": f"https://storage.msgsndr.com/x/{st}-{i:02d}.png"}
        for i, st in enumerate(plan_stages, start=1)]
    (rd / "media_ledger.json").write_text(json.dumps({"images": media_images}), encoding="utf-8")
    manifest = prove_sp_bundle._valid_manifest()
    (rd / "funnel-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # P5/P6/P8/P9 artifact-backed gates (FIX-XC-03b) — materialize the build artifacts
    # through the PROVIDER STUB (A10 / T0-10: the fixture must not be authored by the
    # run under test).
    _write_build_artifacts(rd, manifest, with_receipts=with_receipts)

    nf = rd / ".spa_run_nonce"
    nf.write_text(nonce, encoding="utf-8")
    os.chmod(nf, 0o600)


def _stable_token(kind: str, key: str, n: int) -> str:
    """Deterministic across processes — Python salts str hashing per run, so a
    hash()-derived identifier would make the COMMITTED golden fixture churn on
    every regeneration."""
    return hashlib.sha256(f"{kind}|{key}".encode("utf-8")).hexdigest()[:n]


def _write_build_artifacts(rd: Path, manifest: Dict, *, with_receipts: bool = True) -> None:
    """Create the deterministic P5-P9 artifacts a real run's Skill-6 handoff produces.

    A10 / T0-10 — this writer used to fabricate the documents, delivery and build
    artifacts IN-PROCESS with example-domain URLs and a hardcoded 8.7, and the
    self-test then minted and validated a signed certificate from exactly that
    fixture: the run authored the evidence it was certified on. The artifacts are
    now produced through a PROVIDER STUB module (stub_provider_adapter), which also
    records the delegation receipts — so the fixture comes from a module that is not
    the run under test, and `recorded_by` never resolves to this orchestrator.

    with_receipts=False produces the artifacts WITHOUT receipts, which is the state
    every pre-A10 run is in; the transitional seams must still attest it, and the
    certificate must record delegation_receipts == "absent"."""
    import delegation_receipt as _dr
    import stub_provider_adapter as stub

    if with_receipts:
        # record() appends; a golden example rebuilt twice would otherwise accumulate
        # duplicate receipt lines. FIXTURE regeneration only.
        _dr.reset(rd)

    steps = manifest.get("steps") or []
    for s in steps:
        fp = s.get("fragment_path") if isinstance(s, dict) else None
        if isinstance(fp, str) and fp.strip() and str(s.get("stage", "")).lower() != "bump":
            frag = rd / fp
            frag.parent.mkdir(parents=True, exist_ok=True)
            frag.write_text(
                f"<section data-zhc-fragment=\"{s.get('asset_key', fp)}\">"
                f"<h1>{s.get('step_name', 'section')}</h1><p>approved copy injected here</p></section>\n",
                encoding="utf-8")

    # --- P6 documents: real Docs host + a document identifier per Doc ------------
    docs = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            continue
        key = s.get("asset_key", f"doc-{i}")
        doc_id = "1sTub" + _stable_token("doc", key, 22)
        docs.append({"label": key, "doc_id": doc_id,
                     "url": f"https://docs.google.com/document/d/{doc_id}/edit"})
        if with_receipts:
            stub.emit_one(rd, "P6-DOCS", doc_id, provider="google-docs",
                          operation="documents.create", covers=[doc_id])
    (rd / "drive_docs.json").write_text(json.dumps({"docs": docs}), encoding="utf-8")

    # --- P8 delivery: real Drive folder link + a send receipt identifier ---------
    folder_id = "0AStub" + _stable_token("folder", rd.name, 22)
    send_receipt_id = "<stub-" + _stable_token("send", rd.name, 16) + "@mail.stub>"
    (rd / "delivery.json").write_text(json.dumps({
        "subject": "Your sales page assets are ready",
        "send_receipt_id": send_receipt_id,
        "folder_link": f"https://drive.google.com/drive/folders/{folder_id}"}), encoding="utf-8")
    if with_receipts:
        stub.emit_one(rd, "P8-DELIVER", send_receipt_id, provider="gmail",
                      operation="messages.send", covers=[send_receipt_id])

    # --- P9 build: real GHL preview hosts + a remote build identifier ------------
    built = [s for s in steps if isinstance(s, dict) and s.get("fragment_path")]
    remote_build_id = "fnl_" + _stable_token("build", rd.name, 14)
    preview_urls = [f"https://app.gohighlevel.com/funnels/preview/{remote_build_id}/{s.get('asset_key')}"
                    for s in built]
    (rd / "build_receipt.json").write_text(json.dumps({
        "qc_score": 8.7,
        "remote_build_id": remote_build_id,
        "preview_urls": preview_urls,
        "built_by": "skill-6-ghl-rest-canvas"}), encoding="utf-8")
    if with_receipts:
        stub.emit_one(rd, "P9-HANDOFF", remote_build_id, provider="ghl",
                      operation="funnels.build", covers=[remote_build_id])
        stub.emit(rd, "P2-IMAGES",
                  [im.get("task_id") for im in json.loads(
                      (rd / "media_ledger.json").read_text(encoding="utf-8")).get("images", [])]
                  if (rd / "media_ledger.json").is_file() else [])


def self_test() -> int:
    ok = True
    nonce = "orch-selftest-nonce-777"
    tmp = Path(tempfile.mkdtemp(prefix="spa_orch_selftest_"))
    try:
        rd = tmp / "run-good"
        rd.mkdir()
        _write_valid_run(rd, nonce)

        good, msg = _check_front_door(rd, None, None)
        if not good and "AF-SP56-FRONT-DOOR" in msg:
            print("SELF-TEST ok: missing nonce -> front-door refusal.")
        else:
            ok = False; print(f"SELF-TEST FAIL: missing nonce not refused: {good} {msg}")

        good, msg = _check_front_door(rd, "wrong", None)
        if not good and "AF-SP56-FRONT-DOOR" in msg:
            print("SELF-TEST ok: wrong nonce -> front-door refusal.")
        else:
            ok = False; print(f"SELF-TEST FAIL: wrong nonce not refused: {good} {msg}")

        good, resolved = _check_front_door(rd, nonce, None)
        if not good:
            ok = False; print(f"SELF-TEST FAIL: valid nonce refused: {resolved}")
        else:
            code, cert = orchestrate(rd, resolved)
            if code == EXIT_OK and (rd / "PROCESS-CERTIFICATE.json").exists():
                vcode, vfails = prove_sp_cert.evaluate_cert(
                    json.loads((rd / "PROCESS-CERTIFICATE.json").read_text()), nonce)
                if vcode == prove_sp_cert.EXIT_OK:
                    print("SELF-TEST ok: happy path -> signed certificate minted + validates.")
                else:
                    ok = False; print(f"SELF-TEST FAIL: minted cert invalid: {vfails}")
            else:
                ok = False; print(f"SELF-TEST FAIL: happy path did not certify (code={code}).")

        # no-skip / fail-closed abort — break the copy ledger, expect NO cert
        rd2 = tmp / "run-bad"
        rd2.mkdir()
        _write_valid_run(rd2, nonce)
        import prove_sp_bump_band  # noqa: E402
        bad = json.loads((rd2 / "copy_ledger.json").read_text())
        for a in bad["assets"]:
            if a.get("stage") == "bump":
                a["text"] = "too short"  # breaks bump band + checkbox
        (rd2 / "copy_ledger.json").write_text(json.dumps(bad), encoding="utf-8")
        code, manifest = orchestrate(rd2, nonce)
        if code == EXIT_GATE_FAIL and not (rd2 / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: failing P3 copy gate aborts with NO certificate (fail-closed, no phase skip).")
        else:
            ok = False; print(f"SELF-TEST FAIL: bad run still certified (code={code}).")

        # -------------------------------------------------------------------
        # A10 / T0-09 + T0-10 — the certification seams.
        # -------------------------------------------------------------------
        # (c) The happy-path certificate must RECORD that its delegated phases were
        #     receipt-backed. A certificate that cannot say so cannot be trusted to
        #     mean a provider was contacted.
        cert_obj = json.loads((rd / "PROCESS-CERTIFICATE.json").read_text(encoding="utf-8"))
        if cert_obj.get("delegation_receipts") == "present":
            print("SELF-TEST ok: the signed certificate records delegation_receipts=present.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: certificate delegation_receipts is "
                  f"{cert_obj.get('delegation_receipts')!r}, expected 'present'.")

        # (d) The EXACT T0-10 fixture: caller-authored example-domain document, folder
        #     and preview URLs with a hardcoded score. Each phase must now refuse it.
        rd3 = tmp / "run-placeholders"
        rd3.mkdir()
        _write_valid_run(rd3, nonce)
        (rd3 / "drive_docs.json").write_text(json.dumps(
            {"docs": [{"label": "main", "url": "https://docs.example.com/main"}]}), encoding="utf-8")
        (rd3 / "delivery.json").write_text(json.dumps(
            {"subject": "Your sales page assets are ready",
             "folder_link": "https://drive.example.com/folder/sales-page-assets"}), encoding="utf-8")
        (rd3 / "build_receipt.json").write_text(json.dumps(
            {"qc_score": 8.7, "preview_urls": ["https://preview.example.com/main"]}),
            encoding="utf-8")
        d_ok, d_detail = _docs_gate(rd3)
        v_ok, v_detail = _deliver_gate(rd3)
        b_ok, b_detail = _build_receipt_gate(rd3)
        if (not d_ok and "AF-SP56-DOCS-PLACEHOLDER" in d_detail
                and not v_ok and "AF-SP56-DELIVER-PLACEHOLDER" in v_detail
                and not b_ok and "AF-SP56-BUILD-PLACEHOLDER" in b_detail):
            print("SELF-TEST ok: caller-authored example-domain doc/folder/preview URLs are "
                  "refused at P6, P8 and P9 (were all three accepted).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: placeholder URLs still attested — P6={d_ok}/{d_detail} "
                  f"P8={v_ok}/{v_detail} P9={b_ok}/{b_detail}")

        # (e) P2-IMAGES no longer attests on file existence: an EMPTY ledger the run
        #     wrote is not a delegated image generation.
        rd4 = tmp / "run-emptyledger"
        rd4.mkdir()
        _write_valid_run(rd4, nonce)
        (rd4 / "media_ledger.json").write_text(json.dumps({"images": []}), encoding="utf-8")
        i_ok, i_detail = _images_gate(rd4)
        if not i_ok and "AF-SP56-IMAGES-MISSING" in i_detail:
            print("SELF-TEST ok: P2-IMAGES fails closed on an empty media ledger "
                  "(file existence is no longer proof of delegation).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: P2-IMAGES attested an empty ledger: {i_ok} {i_detail}")

        # (f) SELF-AUTHORED RECEIPT — the run stamps its own delivery receipt. The
        #     subject of a certificate may not author the evidence it is judged on.
        rd5 = tmp / "run-selfauthored-receipt"
        rd5.mkdir()
        _write_valid_run(rd5, nonce, with_receipts=False)
        import delegation_receipt as _dr  # noqa: E402
        deliv = json.loads((rd5 / "delivery.json").read_text(encoding="utf-8"))
        _dr.record(rd5, phase="P8-DELIVER", provider="gmail", operation="messages.send",
                   provider_response_id="msg-selfauthored", http_status=200,
                   remote_id=deliv["send_receipt_id"], covers=[deliv["send_receipt_id"]])
        v_ok, v_detail = _deliver_gate(rd5)
        if not v_ok and "SELF-AUTHORED" in v_detail:
            print("SELF-TEST ok: a delivery receipt the ORCHESTRATOR wrote for itself is "
                  "refused (AF-SP56-DELEG-RECEIPT-SELF-AUTHORED).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: the run certified on a receipt it authored itself: "
                  f"{v_ok} {v_detail}")

        # (g) A receipt-less run (every pre-A10 run) still attests on artifact content,
        #     and its certificate says so — no silent claim of provider evidence.
        rd6 = tmp / "run-noreceipts"
        rd6.mkdir()
        _write_valid_run(rd6, nonce, with_receipts=False)
        code, cert6 = orchestrate(rd6, nonce)
        if code == EXIT_OK and cert6.get("delegation_receipts") == "absent":
            print("SELF-TEST ok: a receipt-less run still certifies (writer-before-requirer) "
                  "and its certificate records delegation_receipts=absent.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: receipt-less run: code={code}, "
                  f"delegation_receipts={cert6.get('delegation_receipts')!r}.")

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
        # The board department MUST be a real, seeded canonical department
        # (23-ai-workforce-blueprint/department-naming-map.json). Skill 56's
        # authoritative owning department per 23-ai-workforce-blueprint/
        # skill-department-map.json is "marketing" (the PRIMARY role
        # sales-page-assets-specialist lives under marketing; web-development is
        # the secondary owner). The prior literal "funnels" was NOT a seeded
        # department anywhere in the fleet, so every card silently misrouted /
        # dropped — the same class of bug as Skill 53's "books". Regression-locked
        # by scripts/test_sp_board_department.py (AST check of this literal).
        return mc_board.begin_run(
            run_dir, slug=run_dir.name,
            title=f"Sales Page Assets — {run_dir.name}",
            department="marketing", persona="Sales Page Assets",
            source="sales-page-assets")
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
    found in the run's media ledger or funnel manifest. Empty when none — never raises."""
    try:
        import re
        for name in ("media_ledger.json", "funnel-manifest.json"):
            p = run_dir / name
            if p.exists():
                m = re.search(r"https?://[^\s\"']+", p.read_text(encoding="utf-8"))
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
        description="Deterministic no-skip Sales Page Assets orchestrator. Requires the "
                    "front-door nonce; emits a signed PROCESS-CERTIFICATE only on all-phases-pass.")
    ap.add_argument("--run-dir", help="the run directory (brief/image_plan/copy/media/manifest)")
    ap.add_argument("--nonce", help="the run-scoped front-door nonce (or SPA_RUN_NONCE)")
    ap.add_argument("--nonce-file", help="path to the nonce file (default <run-dir>/.spa_run_nonce)")
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
