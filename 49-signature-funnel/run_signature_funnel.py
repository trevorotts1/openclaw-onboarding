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
    MUST exist (fail-closed); otherwise the seam is attested as delegated."""
    if required_file is not None:
        p = run_dir / required_file
        if not p.exists():
            return False, f"delegated artifact {required_file} absent (expected for: {label})"
    return True, f"delegated: {label}"


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


# Phase spine — ids + order MUST match prove_sf_cert.EXPECTED_PHASES.
def _phase_gates(run_dir: Path) -> List[Tuple[str, str, Callable[[], Tuple[bool, str]]]]:
    return [
        ("P0-INTAKE", "prove_sf_intake.py",
         lambda: _shell_prover("prove_sf_intake.py", [str(run_dir / "brief.json")])),
        ("P1-COPY", "prove_sf_copy.py",
         lambda: _shell_prover("prove_sf_copy.py", ["--ledger", str(run_dir / "copy_ledger.json")])),
        ("P2-PROMPTS", "prove_sf_prompt_floor.py",
         lambda: _shell_prover("prove_sf_prompt_floor.py", ["--ledger", str(run_dir / "prompt_ledger.json")])),
        ("P3-IMAGES", "kie_image.py",
         lambda: _delegation_seam(run_dir, "media_ledger.json", "Skill 47 kie_image.py (text-to-image + reference_images hook)")),
        ("P4-MEDIA", "ghl_media.py",
         lambda: _delegation_seam(run_dir, "media_ledger.json", "Skill 6 ghl_media.py (media folder + upload)")),
        ("P5-HTML", "html_fragments",
         lambda: _gate_html_fragments(run_dir)),
        ("P6-COMPOSE", "prove_sf_graph.py",
         lambda: _shell_prover("prove_sf_graph.py", ["--graph", str(run_dir / "funnel_graph.json")])),
        ("P7-BUILD", "prove_sf_build.py",
         lambda: _shell_prover("prove_sf_build.py", ["--receipt", str(run_dir / "build_receipt.json")])),
        ("P8-DERIVE", "derived_pages_ledger",
         lambda: _gate_derived_pages(run_dir)),
        ("P9-CERTIFY", "prove_sf_no_pitch.py",
         lambda: _shell_prover("prove_sf_no_pitch.py", ["--ledger", str(run_dir / "media_ledger.json")])),
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


def orchestrate(run_dir: Path, nonce: str) -> Tuple[int, Dict]:
    phases_attested: List[Dict] = []
    gates = _phase_gates(run_dir)
    print(f"== Signature Funnel orchestrator :: run {run_dir} ==")
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
        "delivery": {"publish": "human-approval-required",
                     "preview_only": True,
                     "email_offer": "P10 optional handoff to the Email Skill project after downsell approval"},
    }
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
def _write_valid_run(rd: Path, nonce: str, size: int = 3) -> None:
    import prove_sf_intake, prove_sf_copy, prove_sf_prompt_floor, prove_sf_no_pitch  # noqa: E402
    (rd / "brief.json").write_text(json.dumps(prove_sf_intake._valid_runtime(size)), encoding="utf-8")
    # FIX-XC-02a — the P0 intake gate is fail-closed on persona grounding; the run dir must
    # carry a persona-selection-log naming a registered persona slug (SOP 9.2 Step 0).
    (rd / "persona-selection-log.md").write_text(
        "# persona-selection-log\nselector_ran: true\n- selected_persona: hormozi-100m-offers\n",
        encoding="utf-8")
    (rd / "copy_ledger.json").write_text(json.dumps(prove_sf_copy._valid_ledger()), encoding="utf-8")
    (rd / "prompt_ledger.json").write_text(json.dumps(prove_sf_prompt_floor._valid_ledger()), encoding="utf-8")
    (rd / "media_ledger.json").write_text(json.dumps(prove_sf_no_pitch._valid_ledger()), encoding="utf-8")
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
            department="funnels", persona="Signature Funnel",
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
