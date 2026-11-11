#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_signature_funnel.py — the deterministic Signature Funnel orchestrator (Skill 49).

A no-skip state machine. It runs the fixed phase spine P0..P9 IN ORDER, shells each
phase's fail-closed prover, and — only when EVERY phase passes — emits a signed
PROCESS-CERTIFICATE.json. A failing gate aborts the run (fail-closed) and NO certificate
is written, so an incomplete or non-compliant funnel can never reach Complete.

FRONT DOOR = THE OPERATOR KEY (ENF-16). The orchestrator takes NO caller-supplied secret:
--nonce, --nonce-file and the SF_RUN_NONCE environment variable are all refused with
AF-FUN-FRONT-DOOR (a nonce the caller chose, or a file the caller wrote, proves nothing).
It runs only when the operator key (a >=32-char secret file named by SF_OPERATOR_KEY_FILE,
outside the run dir, mode 0600 — see prove_sf_cert.load_operator_key) is available to the
launching process, and that key — never anything beside the run — keys the certificate HMAC.
A certificate therefore verifies only with the operator key. The content-authoring model is
taken from the harness routing record (routing/model-content-receipt.json, minted and signed
by prove_sf_cert.py --mint-model-receipt), never from SF_CONTENT_* environment variables, and
the delegated image/media phases require harness-signed provider receipts (ENF-17).

DELEGATION SEAMS (never forked here): image generation is delegated to Skill 66 (model
policy) and Skill 74 (the one KIE transport, kie_live_adapter.py); media hosting (P4) and the funnel/page
build (P7) are delegated to the DELIVERY RAIL the brief names (brief.delivery_rail), which records one
operator-key-signed receipt line per hosted image and per built page (schema/delivery-rail-receipt.schema.json).
Skill 49 never imports or resolves the rail: P4 and P7 certify only on those signed lines. Those phases
are attested in order; the image PROVENANCE (Kie taskId + the hosted URL the P4 receipt recorded) is
enforced at P9 by prove_sf_no_pitch.py.

Run-dir inputs:
  brief.json          — locked intake brief        (P0 gate: prove_sf_intake.py)
  copy_ledger.json    — per-page 12-section copy    (P1 gate: prove_sf_copy.py)
  prompt_ledger.json  — image prompts at the prompt-policy band
                        (95-100 percent of the verified maximum;
                        hard floor 80 percent)           (P2 gate: prove_sf_prompt_floor.py)
  media_ledger.json   — images + pages              (P9 gate: prove_sf_no_pitch.py)

stdlib only. Exit 0 = certified, 2 = a phase gate failed, 3 = front-door / usage.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
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
# prove image generation through Skill 74 and upload through the delivery rail was
# satisfied by a file its own subject authored — with no provider ever contacted.
#
# THE FIX (ENF-17): the seams read the ledger's CONTENT — every image record must
# carry a real provider task id (P3) and equal the hosted URL the delivery rail's
# signed receipt recorded (P4) — and the signed receipt store must hold, strictly:
# an absent, unsigned or forged store is a failure, not a state to record. This kills
# "the file exists, therefore a provider ran". The certificate records the store
# state, so it can never imply provider-backed delegation it does not have.
# ---------------------------------------------------------------------------
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
                  content_detail: str, rail: bool = False) -> Tuple[bool, str]:
    try:
        import delegation_receipt
    except ImportError as exc:  # noqa: BLE001 — a missing contract module is fail-closed
        return False, (f"AF-FUN-DELEG-RECEIPT: delegation_receipt.py is not importable "
                       f"({exc}) — the delegated seam {phase} cannot be attested")
    # ENF-17: a client delivery never attests on an absent or hand-written store. Only
    # harness-signed provider receipts (signed by the adapter process under the operator
    # key) count; 'absent' is a failure, not a state to record.
    # rail=True is the delivery-rail form (P4): the same signed check plus the schema in
    # schema/delivery-rail-receipt.schema.json.
    check = delegation_receipt.require_rail if rail else delegation_receipt.require_signed
    ok, detail = check(run_dir, phase, must_cover=keys, af="AF-FUN-DELEG-RECEIPT")
    if not ok:
        return False, detail
    return True, f"delegated: {label} :: {content_detail} :: receipts verified ({detail})"


EMAILS_REL = Path("working") / "emails" / "emails.json"


def _gate_p10_emails(run_dir: Path) -> Tuple[bool, str]:
    """P10-EMAIL — the optional 10 promo emails. The brief's email_offer is `accepted` or `declined`
    (absent = declined). A client who accepted gets no certificate until working/emails/emails.json
    carries a Skill 50 certificate sha (a 64-hex `certificate_sha`); anything else fails
    AF-FUN-P10-EMAILS. A value that is neither word fails too, so a typo can never read as `declined`.
    Returns (ok, 'declined' | 'accepted:<sha>' | the failure)."""
    try:
        offer = json.loads((run_dir / "brief.json").read_text(encoding="utf-8")).get("email_offer", "declined")
    except (OSError, ValueError):
        offer = "declined"
    if offer == "declined":
        return True, "declined"
    if offer != "accepted":
        return False, f"AF-FUN-P10-EMAILS: brief email_offer {offer!r} is neither 'accepted' nor 'declined'"
    try:
        sha = json.loads((run_dir / EMAILS_REL).read_text(encoding="utf-8")).get("certificate_sha")
    except (OSError, ValueError, AttributeError):
        sha = None
    if not (isinstance(sha, str) and len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)):
        return False, (f"AF-FUN-P10-EMAILS: the client accepted the email offer but {EMAILS_REL} is missing or "
                       "carries no Skill 50 certificate sha (a 64-hex certificate_sha)")
    return True, f"accepted:{sha}"


def _gate_p10_emails_value(run_dir: Path, offer: str) -> Tuple[bool, str]:
    """Self-test/probe helper: judge the gate as if the brief said `offer`, on a scratch copy."""
    scratch = Path(tempfile.mkdtemp(prefix="sf_p10_"))
    try:
        (scratch / "brief.json").write_text(json.dumps({"email_offer": offer}), encoding="utf-8")
        return _gate_p10_emails(scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _gate_p3_images(run_dir: Path) -> Tuple[bool, str]:
    """P3-IMAGES — every ledger image must name a real image-provider task id."""
    imgs, err = _ledger_images(run_dir)
    if imgs is None:
        return False, f"AF-FUN-DELEG-IMAGES: {err} (Skill 66 policy + Skill 74 transport produced nothing)"
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
                         "Skill 66 policy + Skill 74 kie_live_adapter.py (text-to-image + reference_images hook)",
                         f"{len(imgs)} image record(s) carry a provider task id")


def _ledger_url(img: Dict) -> str:
    return str(img.get("media_url", img.get("url", ""))).strip()


def _gate_p4_media(run_dir: Path) -> Tuple[bool, str]:
    """P4-MEDIA — every ledger image must carry the hosted URL the delivery rail's signed receipt
    recorded for its key. No host name is recognised here: the rail named in brief.delivery_rail is a
    free string and the receipt, not a URL fingerprint, is the proof something was uploaded."""
    imgs, err = _ledger_images(run_dir)
    if imgs is None:
        return False, f"AF-FUN-DELEG-MEDIA: {err} (the delivery rail recorded nothing)"
    keys = [_image_key(i) for i in imgs]
    ok, detail = _receipt_seam(run_dir, "P4-MEDIA", keys, "delivery-rail receipt (P4)",
                               f"{len(imgs)} image record(s)", rail=True)
    if not ok:
        return False, detail
    import delegation_receipt
    hosted: Dict[str, set] = {}
    for line in delegation_receipt.load(run_dir):
        if str(line.get("phase", "")).strip() == "P4-MEDIA":
            for key in line.get("covers") or []:
                hosted.setdefault(str(key), set()).add(str(line.get("hosted_url", "")).strip())
    bad = [f"{img.get('page_type', '?')}/{img.get('section', '?')}={_ledger_url(img)!r}"
           for img, key in zip(imgs, keys) if _ledger_url(img) not in hosted.get(key, set())]
    if bad:
        return False, (f"AF-FUN-DELEG-MEDIA: {len(bad)} image record(s) carry a URL the delivery rail "
                       f"never recorded for that image (e.g. {bad[:3]}) — an image whose URL is not the "
                       "rail's signed hosted_url is not a delegated upload")
    return True, f"{detail} :: {len(imgs)} ledger URL(s) equal the rail's hosted_url"


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


def _gate_visual(run_dir: Path) -> Tuple[bool, str]:
    """The VISUAL STAGE gate (fix plan B1, unowned requirement G-2).

    Skill 49 had no wireframe/mockup phase at all: the wireframe step lived only as prose in
    SKILL.md ("after P1 copy passes, run scripts/legacy_downsell_images.py"), and the
    orchestrator never invoked it, so the step was skipped silently. This runs the visual
    check as its own named gate — every page must carry the desktop wireframe, the mobile
    wireframe, the visual mockup and the final mockup (prove_sf_build.VISUAL_STAGES) — and
    P7-BUILD calls it FIRST, before the FAB/QC seams, so a run with no visual set cannot
    reach any later proof.
    """
    size = _brief_size(run_dir)
    if size is None:
        if not (run_dir / "brief.json").is_file():
            # A fixture run dir with no brief at all: P7's own AF-FUN-BUILD-SIZE check owns
            # that refusal, so this gate does not pre-empt it with a different code.
            return True, "no brief.json in the run dir; funnel_size is checked by P7-BUILD"
        return False, ("AF-FUN-VISUAL-SIZE: brief funnel_size unresolved — the required page "
                       "set for the visual stages cannot be computed (fail-closed)")
    ok, detail = _shell_prover("prove_sf_build.py",
                               ["--visual-only", "--run-dir", str(run_dir),
                                "--funnel-size", str(size)])
    if ok:
        return True, f"visual stage complete for the {size}-step page set"
    return False, ("AF-FUN-VISUAL-PHASE: the visual stage did not certify — wireframes and final "
                   "mockups are a gated phase, not a prose instruction. " + detail)


def _run_visual_stage(run_dir: Path) -> Tuple[bool, str]:
    """The MANDATORY VISUAL STEP (fix plan B1, second branch).

    When the locked brief asks for it (`visual_stage` in {"auto","required"}), the orchestrator
    runs scripts/legacy_downsell_images.py itself instead of leaving it to prose. The tool is
    invoked, never reimplemented. Nothing is guessed: the paths come from brief.json, and an
    unresolvable brief is refused with the exact command to run by hand.

    A failed invocation is NOT fatal here — the P7 visual gate still refuses to certify a run
    with no visual set, so the attempt can never become a silent skip.
    """
    try:
        brief = json.loads((run_dir / "brief.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True, "no readable brief.json; the P7 visual gate remains the enforcement"
    mode = str(brief.get("visual_stage") or "").strip().lower()
    if mode not in ("auto", "required"):
        return True, "brief does not request a visual step (visual_stage not set)"
    receipt = run_dir / "page-images" / "page-images-receipt.json"
    if receipt.is_file():
        return True, "visual set already present"
    vs = brief.get("visual") if isinstance(brief.get("visual"), dict) else {}
    missing = [k for k in ("skill71_root", "brand_file", "brand_owner") if not vs.get(k)]
    if missing:
        return False, ("AF-FUN-VISUAL-ARGS: brief.visual is missing %s; run "
                       "scripts/legacy_downsell_images.py --ledger <copy_ledger.json> "
                       "--skill71-root <71-dir> --brand-file <brand.json> --brand-owner <client> "
                       "--out-dir <run-dir>/page-images (the P7 visual gate will refuse until it is done)"
                       % ", ".join(missing))
    cmd = [sys.executable, str(_SCRIPTS / "legacy_downsell_images.py"),
           "--ledger", str(run_dir / "copy_ledger.json"),
           "--skill71-root", str(vs["skill71_root"]),
           "--brand-file", str(vs["brand_file"]),
           "--brand-owner", str(vs["brand_owner"]),
           "--out-dir", str(run_dir / "page-images"),  # issue 61: the folder prove_sf_build reads
           "--image-provider", str(vs.get("provider") or "kie")]
    if str(vs.get("provider") or "kie") == "kie" and vs.get("allow_paid") is True:
        cmd.append("--allow-paid")
    if str(vs.get("provider") or "").lower() == "stub" and vs.get("stub_approved_by"):
        cmd += ["--stub-approved-by", str(vs["stub_approved_by"])]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-6:]
    if proc.returncode != 0:
        return False, ("AF-FUN-VISUAL-STEP: legacy_downsell_images.py exited %d: %s"
                       % (proc.returncode, " | ".join(tail)))
    return True, "visual stage produced the wireframe/mockup set"


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
    # Q18 (fix spec M4): the locked brief is handed to the prover so a style_card_id the client chose
    # at intake binds every prompt (AF-FUN-PROMPT-STYLE-CARD); the ledger cannot omit the decision.
    brief = run_dir / "brief.json"
    ok, detail = _shell_prover("prove_sf_prompt_floor.py",
                               ["--ledger", str(run_dir / "prompt_ledger.json"),
                                *(["--brief", str(brief)] if brief.is_file() else [])])
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
    ok, detail = _shell_prover("prove_sf_no_pitch.py", ["--ledger", str(run_dir / "media_ledger.json"),
                                                        "--run-dir", str(run_dir)])
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
# The engine authors its copy in copy_ledger.json then delegates the funnel/page build to
# the delivery rail. On the engine-routed path the rail produced NO template-match receipt, so
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
        URL per page (the existing seam).

    Fix plan B1: the VISUAL STAGE runs FIRST. A run with no wireframe/mockup set must not
    reach the FAB or QC seams at all, so the visual gap is named as its own failure
    (AF-FUN-VISUAL-PHASE) instead of being buried in the build receipt list."""
    visual_ok, visual_detail = _gate_visual(run_dir)
    if not visual_ok:
        return False, visual_detail
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
        ("P3-IMAGES", "kie_live_adapter.py",
         lambda: _gate_p3_images(run_dir)),
        ("P4-MEDIA", "delivery-rail receipt (P4)",
         lambda: _gate_p4_media(run_dir)),
        ("P5-HTML", "html_fragments",
         lambda: _gate_html_fragments(run_dir)),
        ("P6-COMPOSE", "prove_sf_graph.py",
         lambda: _shell_prover("prove_sf_graph.py", ["--graph", str(run_dir / "funnel_graph.json")])),
        ("P7-BUILD", "delivery-rail receipt (P7)",
         lambda: _gate_build(run_dir)),
        ("P8-DERIVE", "derived_pages_ledger",
         lambda: _gate_derived_pages(run_dir)),
        ("P9-CERTIFY", "prove_sf_no_pitch.py",
         lambda: _gate_p9_certify(run_dir)),
    ]


def _check_front_door(run_dir: Path, nonce: Optional[str] = None,
                      nonce_file: Optional[Path] = None) -> Tuple[bool, str]:
    """ENF-16 front door. Returns (True, operator_key) or (False, 'AF-FUN-FRONT-DOOR: ...').
    nonce / nonce_file / SF_RUN_NONCE are parameters only so they can be REFUSED."""
    if nonce is not None or nonce_file is not None:
        return False, ("AF-FUN-FRONT-DOOR: a caller-supplied --nonce / --nonce-file is not accepted — "
                       "the certificate is keyed by the operator key, not by anything the caller wrote")
    if os.environ.get("SF_RUN_NONCE") is not None:
        return False, ("AF-FUN-FRONT-DOOR: SF_RUN_NONCE is not accepted as an input — "
                       "the certificate is keyed by the operator key only")
    key, why = prove_sf_cert.load_operator_key(run_dir)
    if key is None:
        return False, f"AF-FUN-FRONT-DOOR: no operator key for this launch ({why}) — run via the entry shell"
    return True, key


def _check_model_receipt(run_dir: Path, key: str) -> Tuple[bool, str]:
    """The content-authoring model must come from the harness routing record: a receipt minted
    + signed with the operator key for THIS run. Env-named / unsigned receipts fail."""
    p = run_dir / prove_sf_cert.MODEL_RECEIPT_REL
    try:
        receipt = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        receipt = None
    fails = prove_sf_cert.evaluate_model_receipt(receipt, key, run_dir.resolve().name)
    if fails:
        return False, " | ".join(f"{c}: {m}" for c, m in fails)
    return True, f"{receipt.get('model')} ({receipt.get('provider')}, tier {receipt.get('tier')})"


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


def _model_block(run_dir: Path) -> Dict:
    """The authoring model as the harness routing record names it (already verified at the
    front door); covered by the certificate HMAC."""
    try:
        r = json.loads((run_dir / prove_sf_cert.MODEL_RECEIPT_REL).read_text(encoding="utf-8"))
        return {k: r.get(k) for k in ("model", "provider", "tier", "resolved_from", "routing_record_sha256")}
    except (OSError, ValueError):
        return {}


def orchestrate(run_dir: Path, key: str) -> Tuple[int, Dict]:
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
        if pid == "P2-PROMPTS":
            # Fix plan B1 (unowned G-2): the visual stage is a MANDATORY step of the orchestrator,
            # not a sentence in SKILL.md. Issue 52: it runs only AFTER P0, P1 and P2 pass (it can spend
            # with --allow-paid, so never on unproven copy and never on a run whose prompt ledger then
            # fails P2). A failure is recorded and the P7 visual gate still refuses to certify, so it
            # can never be a skip.
            visual_ok, visual_detail = _run_visual_stage(run_dir)
            print(f"  [{'PASS' if visual_ok else 'FAIL':4s}] VISUAL-STEP  (legacy_downsell_images.py) :: {visual_detail}")

    # P10-EMAIL — an accepted email offer must be backed by a Skill 50 certificate sha before we certify.
    email_ok, email_detail = _gate_p10_emails(run_dir)
    print(f"  [{'PASS' if email_ok else 'FAIL':4s}] P10-EMAIL    (emails.json) :: {email_detail}")
    if not email_ok:
        print("ABORT: phase P10-EMAIL failed its fail-closed gate. NO certificate issued.")
        manifest = {"run_id": run_dir.name, "aborted_at": "P10-EMAIL", "phases": phases_attested}
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
        "operator_key_fingerprint": hashlib.sha256(key.encode()).hexdigest()[:16],
        "model_receipt": _model_block(run_dir),
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
                     "email_offer": email_detail.split(":")[0],
                     **({"email_certificate_sha": email_detail.split(":", 1)[1]}
                        if email_detail.startswith("accepted:") else {})},
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
    cert["signature"] = prove_sf_cert.sign(prove_sf_cert.canonical_payload(cert), key)
    (run_dir / "PROCESS-CERTIFICATE.json").write_text(json.dumps(cert, indent=2), encoding="utf-8")

    code, fails = prove_sf_cert.evaluate_cert(cert, key)
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
    (per prove_sf_prompt_floor.required_image_pairs), each with valid Kie + hosted-URL provenance
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


def _write_valid_run(rd: Path, key: str, size: int = 3, receipts: bool = True) -> None:
    """A run dir every phase accepts. `key` is the operator key the process holds (the model
    receipt is minted from a harness routing record with it; provider receipts are emitted by
    the stub adapter, which signs with the same env key). receipts=False leaves the store absent."""
    import prove_sf_intake, prove_sf_copy, prove_sf_prompt_floor, prove_sf_no_pitch  # noqa: E402
    (rd / "brief.json").write_text(json.dumps(prove_sf_intake._valid_runtime(size)), encoding="utf-8")
    # FIX-XC-02a — the P0 intake gate is fail-closed on persona grounding; the run dir must
    # carry a persona-selection-log naming a registered persona slug (SOP 9.2 Step 0).
    (rd / "persona-selection-log.md").write_text(
        "# persona-selection-log\nselector_ran: true\n- selected_persona: hormozi-100m-offers\n",
        encoding="utf-8")
    (rd / "copy_ledger.json").write_text(json.dumps(prove_sf_copy._valid_ledger(size)), encoding="utf-8")
    # FIX-IMG-07: the prompt ledger must cover every required (page_type, section)
    # slot for this size (each prompt still clears the two-floor gate) or P2 fails-closed.
    (rd / "prompt_ledger.json").write_text(
        json.dumps(prove_sf_prompt_floor._floor_passing_full_prompts(size)), encoding="utf-8")
    # FIX-IMG-07: the media ledger must carry an image for every required
    # (page_type, section) slot for this size or P9's coverage assert fails-closed.
    media = prove_sf_no_pitch._valid_ledger()
    media["images"] = _full_coverage_images(size)
    (rd / "media_ledger.json").write_text(json.dumps(media), encoding="utf-8")
    # P6 graph; P8 derived ledger.
    (rd / "funnel_graph.json").write_text(json.dumps(prove_sf_graph._valid_graph(size)), encoding="utf-8")
    (rd / "derived_pages.json").write_text(
        json.dumps(prove_sf_graph._valid_derived_ledger(size)), encoding="utf-8")
    # P5-HTML + P7-BUILD read what the TOOLS wrote, not the receipt (STR-18 / S06-08 / IMG-16): parsed
    # page fragments, the delivery rail's signed P7-BUILD receipt lines and the wireframe + mockup set.
    prove_sf_build.write_valid_run_evidence(rd, size)
    # ENF-16 — the authoring model comes from the HARNESS routing record, signed by the operator key.
    prove_sf_cert.mint_model_receipt(
        rd, {"model": "selftest-strong-model", "provider": "selftest", "tier": "content"}, key)
    # ENF-17 — delegated phases are backed by harness-signed provider receipts (stub adapter).
    # receipts=False leaves the WHOLE store absent (the P7 lines write_valid_run_evidence just emitted go too).
    if receipts:
        _stub_provider_emit(rd, "P3-IMAGES", [_image_key(i) for i in media["images"]])
        _stub_rail_media_emit(rd)
    else:
        (rd / "delegation_receipts.jsonl").unlink(missing_ok=True)


def _stub_provider_emit(run_dir: Path, phase: str, remote_ids: List[str]) -> None:
    """Obtain delegation receipts from a PROVIDER STUB module (A10 / T0-09) instead of
    writing them here. Receipts written from this module would be stamped
    `run_signature_funnel` and refused — which is the property the self-test proves."""
    import stub_provider_adapter
    stub_provider_adapter.emit(run_dir, phase, remote_ids)


def _stub_rail_media_emit(run_dir: Path) -> None:
    """The delivery rail's P4-MEDIA lines, from the same stub module: one signed line per ledger image,
    carrying the hosted URL the ledger names (fixtures only; a real rail records what it uploaded)."""
    import stub_provider_adapter
    imgs, _ = _ledger_images(run_dir)
    stub_provider_adapter.emit_rail(
        run_dir, "P4-MEDIA", [(_image_key(i), {"hosted_url": _ledger_url(i)}) for i in imgs or []])


def self_test() -> int:
    ok = True
    key = "orch-selftest-operator-key-0123456789abcdef"
    tmp = Path(tempfile.mkdtemp(prefix="sf_orch_selftest_"))
    saved_env = {k: os.environ.get(k) for k in ("SF_OPERATOR_KEY_FILE", "SF_RUN_NONCE", "SF_CONTENT_MODEL")}
    key_file = tmp / "operator.key"          # outside every run dir, as the real key must be
    key_file.write_text(key + "\n", encoding="utf-8")
    os.chmod(key_file, 0o600)
    os.environ["SF_OPERATOR_KEY_FILE"] = str(key_file)
    os.environ.pop("SF_RUN_NONCE", None)
    try:
        rd = tmp / "run-good"
        rd.mkdir()
        _write_valid_run(rd, key)

        # (a) ENF-16 front-door refusals — every caller-supplied secret, and a missing operator key.
        for label, args, env in (
                ("--nonce", (key, None), {}),
                ("--nonce-file (a self-made file)", (None, rd / ".sf_run_nonce"), {}),
                ("SF_RUN_NONCE", (None, None), {"SF_RUN_NONCE": key})):
            (rd / ".sf_run_nonce").write_text(key, encoding="utf-8")   # the self-made nonce file
            os.environ.update(env)
            good, msg = _check_front_door(rd, *args)
            os.environ.pop("SF_RUN_NONCE", None)
            if not good and "AF-FUN-FRONT-DOOR" in msg:
                print(f"SELF-TEST ok: {label} -> AF-FUN-FRONT-DOOR.")
            else:
                ok = False; print(f"SELF-TEST FAIL: {label} not refused: {good} {msg}")
        os.environ.pop("SF_OPERATOR_KEY_FILE")
        good, msg = _check_front_door(rd, None, None)
        os.environ["SF_OPERATOR_KEY_FILE"] = str(key_file)
        if not good and "AF-FUN-FRONT-DOOR" in msg:
            print("SELF-TEST ok: no operator key -> AF-FUN-FRONT-DOOR (a self-made nonce file is not a front door).")
        else:
            ok = False; print(f"SELF-TEST FAIL: missing operator key not refused: {good} {msg}")

        # (b) model receipt: the SF_CONTENT_MODEL env var is never a source; an unsigned
        #     env-style receipt (the old shell's shape) is refused.
        os.environ["SF_CONTENT_MODEL"] = "deepseek-v3-chat"
        rdb = tmp / "run-envmodel"
        rdb.mkdir()
        _write_valid_run(rdb, key)
        (rdb / "routing" / "model-content-receipt.json").write_text(json.dumps(
            {"role": "content", "resolved_from": "client-provider-chain", "model": "deepseek-v3-chat",
             "provider": "deepseek", "tier": "content"}), encoding="utf-8")
        good, msg = _check_model_receipt(rdb, key)
        os.environ.pop("SF_CONTENT_MODEL", None)
        good2, msg2 = _check_model_receipt(tmp / "run-no-routing-dir", key)
        if not good and not good2 and "AF-FUN-MODEL-TIER" in msg:
            print("SELF-TEST ok: env-named / absent model receipt -> AF-FUN-MODEL-TIER.")
        else:
            ok = False; print(f"SELF-TEST FAIL: self-reported model receipt accepted: {good} {msg} / {good2}")

        # (c) full happy path -> certified + cert validates ONLY with the operator key
        good, resolved = _check_front_door(rd, None, None)
        mgood, mmsg = _check_model_receipt(rd, key)
        if not good or not mgood:
            ok = False; print(f"SELF-TEST FAIL: valid front door refused: {resolved} / {mmsg}")
        else:
            code, cert = orchestrate(rd, resolved)
            if code == EXIT_OK and (rd / "PROCESS-CERTIFICATE.json").exists():
                minted = json.loads((rd / "PROCESS-CERTIFICATE.json").read_text())
                vcode, vfails = prove_sf_cert.evaluate_cert(minted, key)
                wcode, _ = prove_sf_cert.evaluate_cert(minted, "the-key-the-ai-chose-0123456789abcdef")
                ncode, _ = prove_sf_cert.evaluate_cert(minted, None)
                if vcode == prove_sf_cert.EXIT_OK and wcode != prove_sf_cert.EXIT_OK \
                        and ncode != prove_sf_cert.EXIT_OK:
                    print("SELF-TEST ok: happy path -> certificate minted; it verifies with the operator "
                          "key and FAILS with any other key or none.")
                else:
                    ok = False; print(f"SELF-TEST FAIL: minted cert invalid / verifies without the key: {vfails}")
            else:
                ok = False; print(f"SELF-TEST FAIL: happy path did not certify (code={code}).")

        # (c2) P10-EMAIL — accepted offer: no emails file -> abort, NO cert; with a cert sha -> certified
        #      and the certificate names the state; declined (absent) is recorded as declined.
        rde = tmp / "run-emails"
        rde.mkdir()
        _write_valid_run(rde, key)
        brief = json.loads((rde / "brief.json").read_text(encoding="utf-8"))
        brief["email_offer"] = "accepted"
        (rde / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
        code, _ = orchestrate(rde, key)
        refused = code == EXIT_GATE_FAIL and not (rde / "PROCESS-CERTIFICATE.json").exists()
        (rde / EMAILS_REL).parent.mkdir(parents=True, exist_ok=True)
        (rde / EMAILS_REL).write_text(json.dumps({"certificate_sha": "ab" * 32, "emails": []}), encoding="utf-8")
        code, _ = orchestrate(rde, key)
        named = {}
        if (rde / "PROCESS-CERTIFICATE.json").exists():
            named = json.loads((rde / "PROCESS-CERTIFICATE.json").read_text(encoding="utf-8")).get("delivery", {})
        declined = json.loads((rd / "PROCESS-CERTIFICATE.json").read_text(encoding="utf-8")).get("delivery", {}) \
            if (rd / "PROCESS-CERTIFICATE.json").exists() else {}
        typo_ok, typo_msg = _gate_p10_emails_value(rde, "accept")
        if refused and code == EXIT_OK and named.get("email_offer") == "accepted" \
                and named.get("email_certificate_sha") == "ab" * 32 and declined.get("email_offer") == "declined" \
                and not typo_ok and "AF-FUN-P10-EMAILS" in typo_msg:
            print("SELF-TEST ok: P10-EMAIL — accepted offer without a Skill 50 certificate sha aborts "
                  "(AF-FUN-P10-EMAILS, no certificate); with it the certificate names accepted; absent = declined.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: P10-EMAIL (refused={refused}, code={code}, named={named}, declined={declined}, typo={typo_msg})")

        # (d) no-skip / fail-closed abort — break the copy ledger, expect NO cert
        rd2 = tmp / "run-bad"
        rd2.mkdir()
        _write_valid_run(rd2, key)
        import prove_sf_copy  # noqa: E402
        bad = prove_sf_copy._valid_ledger()
        bad["pages"][0]["sections"] = [s for s in bad["pages"][0]["sections"] if s.get("section") != 3]
        (rd2 / "copy_ledger.json").write_text(json.dumps(bad), encoding="utf-8")
        code, manifest = orchestrate(rd2, key)
        if code == EXIT_GATE_FAIL and not (rd2 / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: failing P1 gate aborts with NO certificate (fail-closed, no phase skip).")
        else:
            ok = False; print(f"SELF-TEST FAIL: bad run still certified (code={code}).")

        # (e) FIX-XC-03a — the once-no-op P5-HTML now fails closed: drop a page fragment.
        rd3 = tmp / "run-nohtml"
        rd3.mkdir()
        _write_valid_run(rd3, key)
        (rd3 / "pages" / "thank-you.fragment.html").unlink()
        code, _ = orchestrate(rd3, key)
        if code == EXIT_GATE_FAIL and not (rd3 / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: missing HTML fragment aborts at P5 with NO certificate (was a no-op).")
        else:
            ok = False; print(f"SELF-TEST FAIL: P5 no-op — run with a missing fragment still certified (code={code}).")

        # (f) FIX-XC-03a — the once-no-op P6-COMPOSE now fails closed: remove funnel_graph.json.
        rd4 = tmp / "run-nograph"
        rd4.mkdir()
        _write_valid_run(rd4, key)
        (rd4 / "funnel_graph.json").unlink()
        code, _ = orchestrate(rd4, key)
        if code == EXIT_GATE_FAIL and not (rd4 / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: missing funnel_graph aborts at P6 with NO certificate (was a no-op).")
        else:
            ok = False; print(f"SELF-TEST FAIL: P6 no-op — run with no funnel graph still certified (code={code}).")

        # (g0) FIX-IMG-07 — a partial prompt ledger (2 of N required slots) aborts at
        # P2 with AF-FUN-PROMPT-COVERAGE and NO certificate (the floor gate still clears).
        rd0 = tmp / "run-shortprompts"
        rd0.mkdir()
        _write_valid_run(rd0, key)
        import prove_sf_prompt_floor as _pf  # noqa: E402
        (rd0 / "prompt_ledger.json").write_text(json.dumps(_pf._valid_ledger()), encoding="utf-8")
        code, manifest0 = orchestrate(rd0, key)
        aborted_p2 = isinstance(manifest0, dict) and manifest0.get("aborted_at") == "P2-PROMPTS"
        if code == EXIT_GATE_FAIL and not (rd0 / "PROCESS-CERTIFICATE.json").exists() and aborted_p2:
            print("SELF-TEST ok: partial prompt ledger aborts at P2 (AF-FUN-PROMPT-COVERAGE), NO certificate.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: under-covered prompt ledger still advanced "
                  f"(code={code}, aborted_at={manifest0.get('aborted_at') if isinstance(manifest0, dict) else '?'}).")

        # (g0b) Q18 (fix spec M4) — the brief names a Skill 45 style card but no prompt embeds it:
        # the run aborts at P2 with AF-FUN-PROMPT-STYLE-CARD and NO certificate (it used to certify).
        rdq = tmp / "run-style-card-missing"
        rdq.mkdir()
        _write_valid_run(rdq, key)
        briefq = json.loads((rdq / "brief.json").read_text(encoding="utf-8"))
        briefq.setdefault("answers", {})["q18_style_card_id"] = _pf.FIXTURE_CARD_ID
        (rdq / "brief.json").write_text(json.dumps(briefq), encoding="utf-8")
        with _pf.fixture_library():
            code, manifestq = orchestrate(rdq, key)
        last_q = (manifestq.get("phases") or [{}])[-1].get("detail", "") if isinstance(manifestq, dict) else ""
        if (code == EXIT_GATE_FAIL and not (rdq / "PROCESS-CERTIFICATE.json").exists()
                and manifestq.get("aborted_at") == "P2-PROMPTS" and "AF-FUN-PROMPT-STYLE-CARD" in last_q):
            print("SELF-TEST ok: a brief naming a style card the prompts never embed aborts at P2 "
                  "(AF-FUN-PROMPT-STYLE-CARD), NO certificate.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: Q18 style card not enforced at P2 (code={code}, detail={last_q[:160]!r}).")

        # (g) FIX-IMG-07 — a partial media ledger (2 of N required images) aborts at
        # P9 with AF-FUN-IMG-COVERAGE and NO certificate.
        rd5 = tmp / "run-undercovered"
        rd5.mkdir()
        _write_valid_run(rd5, key)
        media = json.loads((rd5 / "media_ledger.json").read_text(encoding="utf-8"))
        media["images"] = media["images"][:2]  # keep provenance valid, drop coverage
        (rd5 / "media_ledger.json").write_text(json.dumps(media), encoding="utf-8")
        code, manifest5 = orchestrate(rd5, key)
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
        _write_valid_run(rdj, key)
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

        # (k) P4-MEDIA no longer attests on file existence: a ledger URL the delivery rail's signed
        #     receipt never recorded for that image is not an upload (no host-name fingerprint is used).
        rdk = tmp / "run-offhost"
        rdk.mkdir()
        _write_valid_run(rdk, key)
        led = json.loads((rdk / "media_ledger.json").read_text(encoding="utf-8"))
        led["images"][0]["media_url"] = "https://cdn.somewhere-else.test/hero.png"
        (rdk / "media_ledger.json").write_text(json.dumps(led), encoding="utf-8")
        g_ok, g_detail = _gate_p4_media(rdk)
        if not g_ok and "AF-FUN-DELEG-MEDIA" in g_detail:
            print("SELF-TEST ok: P4-MEDIA fails closed on a ledger URL that differs from the rail's hosted_url "
                  "(AF-FUN-DELEG-MEDIA).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: P4-MEDIA attested a URL the rail never recorded: {g_ok} {g_detail}")

        # (k2) a P4 line in the old provider shape (signed, but no hosted_url) breaks the delivery-rail
        #      schema: the rail must say WHICH URL it hosted, not just that it ran.
        rdk2 = tmp / "run-rail-schema"
        rdk2.mkdir()
        _write_valid_run(rdk2, key, receipts=False)
        led = json.loads((rdk2 / "media_ledger.json").read_text(encoding="utf-8"))
        _stub_provider_emit(rdk2, "P4-MEDIA", [_image_key(i) for i in led["images"]])
        g_ok, g_detail = _gate_p4_media(rdk2)
        if not g_ok and "AF-FUN-DELEG-RECEIPT-SCHEMA" in g_detail:
            print("SELF-TEST ok: P4-MEDIA fails closed on a signed line with no hosted_url "
                  "(AF-FUN-DELEG-RECEIPT-SCHEMA).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: P4-MEDIA attested a line that breaks the rail schema: {g_ok} {g_detail}")

        # (l) SELF-AUTHORED RECEIPT — the run stamps its own provider receipt. The
        #     subject of a certificate may not author the evidence it is judged on,
        #     so the seam must REFUSE it (and must not be more permissive than the
        #     absent case, which is the whole shape of the A10 defect).
        rdl = tmp / "run-selfauthored-receipt"
        rdl.mkdir()
        _write_valid_run(rdl, key, receipts=False)
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
        _write_valid_run(rdm, key, receipts=False)
        led = json.loads((rdm / "media_ledger.json").read_text(encoding="utf-8"))
        _stub_provider_emit(rdm, "P3-IMAGES", [_image_key(i) for i in led["images"]])
        _stub_rail_media_emit(rdm)
        g_ok, g_detail = _gate_p3_images(rdm)
        g_ok4, g_detail4 = _gate_p4_media(rdm)
        if g_ok and g_ok4 and "receipts verified" in g_detail and "receipts verified" in g_detail4:
            print("SELF-TEST ok: provider-stub receipts verify at P3 and P4 "
                  "(fixture produced by a stub, never by the run under test).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: stub-provider receipts not verified: "
                  f"P3={g_ok}/{g_detail} P4={g_ok4}/{g_detail4}")
        rdabs = tmp / "run-no-receipt-store"
        rdabs.mkdir()
        _write_valid_run(rdabs, key, receipts=False)
        if _delegation_receipt_state(rdm) == "present" and _delegation_receipt_state(rdabs) == "absent":
            print("SELF-TEST ok: the certificate records delegation_receipts present/absent "
                  "(a certificate cannot imply provider evidence it does not carry).")
        else:
            ok = False
            print("SELF-TEST FAIL: delegation_receipts certificate state is wrong "
                  f"(stub={_delegation_receipt_state(rdm)}, plain={_delegation_receipt_state(rdabs)}).")

        # (m2) ENF-17 — an ABSENT receipt store is a FAILURE for a client delivery (was: attest +
        #      record "absent"), and the whole run aborts at P3 with NO certificate.
        g_ok, g_detail = _gate_p3_images(rdabs)
        code, manifestabs = orchestrate(rdabs, key)
        if not g_ok and "ABSENT" in g_detail and code == EXIT_GATE_FAIL \
                and manifestabs.get("aborted_at") == "P3-IMAGES" \
                and not (rdabs / "PROCESS-CERTIFICATE.json").exists():
            print("SELF-TEST ok: an absent delegation receipt store fails P3 (AF-FUN-DELEG-RECEIPT-ABSENT), NO certificate.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: run certified/attested with the receipt store absent: {g_ok} {g_detail}")

        # (m3) ENF-17 — a store the AI wrote by hand (honest-looking, unsigned) is refused.
        rdh = tmp / "run-handwritten-store"
        rdh.mkdir()
        _write_valid_run(rdh, key, receipts=False)
        led = json.loads((rdh / "media_ledger.json").read_text(encoding="utf-8"))
        with (rdh / "delegation_receipts.jsonl").open("w", encoding="utf-8") as fh:
            for im in led["images"]:
                fh.write(json.dumps({"phase": "P3-IMAGES", "provider": "kie", "operation": "createTask",
                                     "provider_response_id": "kie-resp-" + _image_key(im), "http_status": 200,
                                     "remote_id": _image_key(im), "covers": [_image_key(im)],
                                     "recorded_by": "kie_image_adapter", "at": _now()}) + "\n")
        g_ok, g_detail = _gate_p3_images(rdh)
        if not g_ok and "UNSIGNED" in g_detail:
            print("SELF-TEST ok: a hand-written (unsigned) receipt store is refused (AF-FUN-DELEG-RECEIPT-UNSIGNED).")
        else:
            ok = False; print(f"SELF-TEST FAIL: hand-written receipt store attested: {g_ok} {g_detail}")

        # (n) A receipt that covers only SOME of the ledger's rows does not attest the
        #     rest — omission inside a receipt store is still omission.
        rdn = tmp / "run-partial-receipt"
        rdn.mkdir()
        _write_valid_run(rdn, key, receipts=False)
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
        _write_valid_run(rdo, key, size=7)
        rcpt = json.loads((rdo / "build_receipt.json").read_text(encoding="utf-8"))
        rcpt["pages"] = [p for p in rcpt["pages"]
                         if p.get("page_type") in ("main", "upsell", "thank-you")]
        (rdo / "build_receipt.json").write_text(json.dumps(rcpt), encoding="utf-8")
        code, manifesto = orchestrate(rdo, key)
        aborted_p7 = isinstance(manifesto, dict) and manifesto.get("aborted_at") == "P7-BUILD"
        if code == EXIT_GATE_FAIL and not (rdo / "PROCESS-CERTIFICATE.json").exists() and aborted_p7:
            print("SELF-TEST ok: a 7-step funnel with a 3-page build receipt aborts at P7 "
                  "(AF-FUN-BUILD-PAGESET), NO certificate.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: incomplete funnel build still certified (code={code}, "
                  f"aborted_at={manifesto.get('aborted_at') if isinstance(manifesto, dict) else '?'}).")

        # (p) G-2/G-17 + issue 52 — the visual step (which can spend with --allow-paid) runs only after
        #     P2-PROMPTS passes. Spy on subprocess.run and keep the WHOLE call log in order: a failing copy
        #     ledger and a failing prompt ledger -> zero calls to legacy_downsell_images; a passing run ->
        #     exactly one, AFTER both P2 provers (floor + coverage) have run, and no --allow-paid command
        #     appears anywhere in the log before that point.
        import types
        real_run = subprocess.run
        for label, break_it, want in (("failing copy", "copy", 0), ("failing prompts", "prompts", 0),
                                      ("passing run", None, 1)):
            rdp = tmp / ("run-visual-" + label.replace(" ", "-"))
            rdp.mkdir()
            _write_valid_run(rdp, key)
            shutil.rmtree(rdp / "page-images", ignore_errors=True)
            brief = json.loads((rdp / "brief.json").read_text(encoding="utf-8"))
            brief["visual_stage"] = "required"
            brief["visual"] = {"skill71_root": str(tmp), "brand_file": str(tmp / "b.json"),
                               "brand_owner": "selftest", "provider": "kie", "allow_paid": True}
            (rdp / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
            if break_it == "copy":
                (rdp / "copy_ledger.json").write_text("{}", encoding="utf-8")
            if break_it == "prompts":  # clears the floor gate, fails the coverage cross-check
                import prove_sf_prompt_floor as _ppf  # noqa: E402
                (rdp / "prompt_ledger.json").write_text(json.dumps(_ppf._valid_ledger()), encoding="utf-8")
            log: List[List[str]] = []

            def _spy(cmd, *a, **kw):
                log.append([str(c) for c in cmd])
                if any("legacy_downsell_images" in str(c) for c in cmd):
                    return types.SimpleNamespace(returncode=0, stdout="", stderr="")
                return real_run(cmd, *a, **kw)
            subprocess.run = _spy
            try:
                orchestrate(rdp, key)
            finally:
                subprocess.run = real_run
            legacy = [i for i, c in enumerate(log) if any("legacy_downsell_images" in x for x in c)]
            floor = [i for i, c in enumerate(log) if any("prove_sf_prompt_floor" in x for x in c)]
            if len(legacy) != want:
                ok = False
                print(f"SELF-TEST FAIL: {label} -> {len(legacy)} legacy_downsell_images call(s), wanted {want}.")
            elif want == 1 and not (len(floor) >= 2 and legacy[0] > floor[1]
                                    and not any("--allow-paid" in x for c in log[:floor[1] + 1] for x in c)):
                ok = False
                print(f"SELF-TEST FAIL: {label} -> the visual step did not run AFTER both P2 provers, or a "
                      f"--allow-paid command came before P2 passed (legacy call at {legacy}, P2 provers at {floor}).")
            else:
                print(f"SELF-TEST ok: {label} -> {want} legacy_downsell_images call(s)"
                      + (f", after both P2 provers, no --allow-paid before P2 (call log: P2 at {floor[:2]}, "
                         f"visual step at {legacy[0]})." if want else "."))

        # (p2) issue 61 — the visual step must write where the P7 gate reads. No spy: a REAL stub-provider run
        #      of legacy_downsell_images.py into a temp run dir (the stub is approved by a Command Center
        #      record from a loopback fake, and this self-test is the test harness that sets
        #      SKILL71_FIXTURE_RUN), then prove_sf_build.visual_direction_violations (the function behind
        #      --visual-only) must find the whole wireframe/mockup set and ask only for final-mockups.
        skill71 = _SCRIPT_DIR.parent / "71-blackceo-signature-page"
        golden = _SCRIPT_DIR / "examples" / "golden-daybreak" / "copy_ledger.json"
        if not (skill71 / "scripts" / "run_governed_stage.py").is_file() or not golden.is_file():
            ok = False
            print(f"SELF-TEST FAIL: the real visual-step case needs Skill 71 ({skill71}) and the golden copy "
                  "ledger beside Skill 49; one is missing, so the --out-dir fix cannot be proven here.")
        else:
            sys.path.insert(0, str(_SCRIPT_DIR / "tests"))  # the loopback stand-in lives in tests/, which the bypass scan skips
            import fake_command_center  # noqa: E402
            rdq = tmp / "run-visual-real"
            rdq.mkdir()
            _write_valid_run(rdq, key)
            shutil.rmtree(rdq / "page-images", ignore_errors=True)
            (rdq / "copy_ledger.json").write_text(
                json.dumps(dict(json.loads(golden.read_text(encoding="utf-8")), funnel_size=3)), encoding="utf-8")
            with fake_command_center.FakeCommandCenter() as cc:
                brief = json.loads((rdq / "brief.json").read_text(encoding="utf-8"))
                brief["visual_stage"] = "required"
                brief["visual"] = {"skill71_root": str(skill71),
                                   "brand_file": str(skill71 / "assets" / "brand" / "blackceo-brand.json"),
                                   "brand_owner": "blackceo", "provider": "stub",
                                   "stub_approved_by": cc.mint("stub_render", _sha256_file(rdq / "copy_ledger.json"))}
                (rdq / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
                env_keys = (*cc.env(), "SKILL71_FIXTURE_RUN")
                saved_visual_env = {k: os.environ.get(k) for k in env_keys}
                os.environ.update(cc.env())
                os.environ["SKILL71_FIXTURE_RUN"] = "1"
                try:
                    ran_ok, ran_detail = _run_visual_stage(rdq)
                    found = prove_sf_build.visual_direction_violations(rdq, 3)
                finally:
                    for k, v in saved_visual_env.items():
                        if v is None:
                            os.environ.pop(k, None)
                        else:
                            os.environ[k] = v
            receipt_there = (rdq / "page-images" / "page-images-receipt.json").is_file()
            only_final = bool(found) and all(c == "AF-FUN-BUILD-VISUAL" and "final-mockups" in m for c, m in found)
            if ran_ok and receipt_there and only_final and not (rdq / "page-images-receipt.json").exists():
                print("SELF-TEST ok: a real stub run writes <run>/page-images/ and the P7 visual gate reads it "
                      "(only final-mockups, the client-gated stage, is still asked for).")
            else:
                ok = False
                print(f"SELF-TEST FAIL: the visual step's output is not where P7 reads it: ran_ok={ran_ok} "
                      f"({ran_detail}), receipt in page-images/={receipt_there}, violations={found[:3]}")

        print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
        return 0 if ok else 1
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
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
        description="Deterministic no-skip Signature Funnel orchestrator. Needs the operator key "
                    "(SF_OPERATOR_KEY_FILE); emits a signed PROCESS-CERTIFICATE only on all-phases-pass.")
    ap.add_argument("--run-dir", help="the run directory (brief/copy/prompt/media ledgers)")
    # ENF-16: declared ONLY so they can be refused with AF-FUN-FRONT-DOOR (not an argparse usage error).
    ap.add_argument("--nonce", help="REMOVED: refused (AF-FUN-FRONT-DOOR)")
    ap.add_argument("--nonce-file", help="REMOVED: refused (AF-FUN-FRONT-DOOR)")
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
    mgood, mmsg = _check_model_receipt(run_dir, resolved)
    if not mgood:
        print(f"AF-FUN-FRONT-DOOR: content-authoring model receipt refused :: {mmsg}")
        return EXIT_FRONT_DOOR

    _mc_task = _mc_board_begin(run_dir)
    code, _ = orchestrate(run_dir, resolved)
    if code == EXIT_OK:
        _mc_board_done(run_dir, _mc_task)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
