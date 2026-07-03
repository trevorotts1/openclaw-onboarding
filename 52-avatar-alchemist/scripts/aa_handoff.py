#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_handoff.py — deterministic downstream-handoff manifest for a DELIVERED
Avatar-Alchemist BRAND package (Skill 52).

Automates the "Downstream handoffs" routing that INSTRUCTIONS.md / HOW-TO-USE.md
have carried only as prose. Once a package has been delivered AND certified
(aa_delivery_gate.py wrote PROCESS-CERTIFICATE.json into the delivery folder),
this emits two artifacts INTO that folder:

  * HANDOFF.json  — machine-readable next-step routing: for each downstream
                    skill, the exact shipped deliverable files it consumes,
                    each bound to the sha256 aa_package.py recorded in
                    MANIFEST.json, so an orchestrator can trigger the next step
                    deterministically (no re-reading, no guessing).
  * HANDOFF.md    — the same routing as a human next-step checklist.

The documented routing (single source of truth: INSTRUCTIONS.md):
  * Skill 38 (conversational-ai-system) <- the 3 booking-bot docs (+ bot-prep)
  * Skill 48 (facebook-ad-generator)    <- Top-39 Ad Angles + FB Headline/Primary
                                           Text + FB Targeting Intelligence
  * Skill 47 (movie-producer)           <- the two image-prompt docs
  * Skill  6 (ghl-install-pages)        <- the Landing Page (the one GHL rail)

version=book intake is routed OUT at Gate 0 (aa_intake_gate.py -> Skill 53); a
BRAND package therefore never carries a book handoff — that is recorded only as
a note here.

Design guarantees (so this can sit in scripts/ next to the fail-closed provers
without weakening anything):
  * NO LLM, NO network, NO egress, stdlib only — a pure read-of-the-package ->
    write-two-files transform, exactly like aa_package.py. It is scanned by
    aa_egress_gate.py like every other prover and stays clean.
  * It NEVER signs, re-signs, or re-issues the delivery certificate (that is
    aa_delivery_gate.py's sole, HMAC-keyed job). It only REQUIRES that a
    certificate is already present + parses as this skill's certificate, so a
    handoff can never be minted for an uncertified / undelivered folder
    (no-false-handoff). It runs strictly AFTER delivery, so it is bound by the
    certificate rather than binding it, and cannot affect `--verify-cert`.
  * Deterministic output (no wall-clock field): provenance is bound by the
    sha256 of the source MANIFEST.json and PROCESS-CERTIFICATE.json bytes.
  * Fail-closed on an INCOMPLETE package: if a routed deliverable the docs
    promise downstream is not present in MANIFEST.json + on disk, it refuses
    (AF-AV-HANDOFF-INCOMPLETE) rather than emit a partial handoff.

Exit 0 = handoff written, 2 = handoff violation (uncertified / incomplete
package), 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CERT_NAME = "PROCESS-CERTIFICATE.json"
CERT_KIND = "avatar-alchemist-brand-run"

# The documented downstream routing (INSTRUCTIONS.md "Downstream handoffs").
# `required` deliverables MUST be present in the certified package or the
# handoff fails closed; `supporting` deliverables are attached when present but
# never block. Keys are the deliverable BASE names (the AA-PIPELINE-MANIFEST.json
# `deliverables` keys), resolved to the actual `-<First>_<Last>.md` filenames.
HANDOFF_ROUTES: List[Dict[str, Any]] = [
    {
        "skill_number": 38,
        "skill_dir": "38-conversational-ai-system",
        "skill_name": "conversational-ai-system",
        "purpose": "Conversational-AI playbook input: the 3 booking-bot conversation docs.",
        "required": [
            "AI_Booking_Bot_Intelligence",
            "AI_Post_Booking_Bot_Intelligence",
            "Rescheduling_Booking_Bot_Intelligence",
        ],
        "supporting": ["AI_Bot_Prep_Doc_Intelligence"],
    },
    {
        "skill_number": 48,
        "skill_dir": "48-facebook-ad-generator",
        "skill_name": "facebook-ad-generator",
        "purpose": "Facebook ad generation: angles + primary-text copy + audience targeting.",
        "required": [
            "Top_39_Suggested_Ad_Angles",
            "Facebook_Headline_and_Primary_Text_Ad_Copy_Writer",
            "Facebook_Targeting_Intelligence",
        ],
        "supporting": [],
    },
    {
        "skill_number": 47,
        "skill_dir": "47-movie-producer",
        "skill_name": "movie-producer",
        "purpose": "Image generation from the two image-prompt docs.",
        "required": [
            "Top_39_Suggested_Image_Prompts",
            "Landing_Page_Image_Prompts",
        ],
        "supporting": [],
    },
    {
        "skill_number": 6,
        "skill_dir": "06-ghl-install-pages",
        "skill_name": "ghl-install-pages",
        "purpose": "GHL landing-page install / delivery (the one GHL rail).",
        "required": ["Landing_Page"],
        "supporting": [],
    },
]

BOOK_ROUTE_NOTE = (
    "version=book intake is routed to Skill 53 (avatar-alchemist-book) at Gate 0 "
    "(aa_intake_gate.py); a BRAND package never carries a book handoff."
)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _base_name(filename: str, client_label: str) -> str:
    """Strip the -<First>_<Last>.md suffix that aa_package.py appends."""
    suffix = f"-{client_label}.md"
    if filename.endswith(suffix):
        return filename[: -len(suffix)]
    return filename[:-3] if filename.endswith(".md") else filename


def _load_manifest(deliver_dir: Path) -> Tuple[Optional[Dict[str, Any]], List[Tuple[str, str]]]:
    p = deliver_dir / "MANIFEST.json"
    if not p.is_file():
        return None, [("AF-AV-HANDOFF-INCOMPLETE",
                        f"no MANIFEST.json in {deliver_dir} — cannot build a handoff for an unpackaged folder")]
    try:
        man = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, [("AF-AV-HANDOFF-INCOMPLETE", f"MANIFEST.json does not parse: {exc}")]
    if not isinstance(man.get("files"), dict) or not man.get("client_label"):
        return None, [("AF-AV-HANDOFF-INCOMPLETE",
                        "MANIFEST.json is missing 'files' / 'client_label' (not an aa_package.py manifest)")]
    return man, []


def _require_certificate(deliver_dir: Path) -> List[Tuple[str, str]]:
    """A handoff is only ever minted for a DELIVERED + CERTIFIED package. This
    does NOT re-verify the HMAC signature (aa_delivery_gate.py owns that); it
    refuses only when no valid certificate FILE is present, so a handoff cannot
    be produced for an undelivered folder."""
    p = deliver_dir / CERT_NAME
    if not p.is_file():
        return [("AF-AV-HANDOFF-UNCERTIFIED",
                  f"no {CERT_NAME} in {deliver_dir} — a handoff is only produced AFTER the delivery gate "
                  f"certifies the package (run aa_delivery_gate.py first)")]
    try:
        cert = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [("AF-AV-HANDOFF-UNCERTIFIED", f"{CERT_NAME} does not parse: {exc}")]
    if cert.get("certificate") != CERT_KIND:
        return [("AF-AV-HANDOFF-UNCERTIFIED",
                  f"{CERT_NAME} is not a {CERT_KIND!r} certificate (got {cert.get('certificate')!r})")]
    return []


def build_handoff(deliver_dir: Path) -> Tuple[Optional[Dict[str, Any]], List[Tuple[str, str]]]:
    """Resolve the documented routing against the packaged MANIFEST.json. Pure;
    no writes, no cert requirement (see write_handoff for the delivered gate)."""
    man, mv = _load_manifest(deliver_dir)
    if man is None:
        return None, mv
    client_label = man["client_label"]
    files: Dict[str, Any] = man["files"]

    # base deliverable name -> {file, sha256}, verified to exist on disk.
    by_base: Dict[str, Dict[str, str]] = {}
    violations: List[Tuple[str, str]] = []
    for fn, meta in files.items():
        if not (deliver_dir / fn).is_file():
            violations.append(("AF-AV-HANDOFF-INCOMPLETE",
                                f"MANIFEST.json claims {fn!r} but it is absent on disk — incomplete package"))
            continue
        by_base[_base_name(fn, client_label)] = {"file": fn, "sha256": str(meta.get("sha256", ""))}

    targets: List[Dict[str, Any]] = []
    for route in HANDOFF_ROUTES:
        inputs: List[Dict[str, str]] = []
        missing: List[str] = []
        for base in route["required"]:
            hit = by_base.get(base)
            if hit is None:
                missing.append(base)
            else:
                inputs.append({"deliverable": base, "file": hit["file"], "sha256": hit["sha256"]})
        if missing:
            violations.append(("AF-AV-HANDOFF-INCOMPLETE",
                                f"Skill {route['skill_number']} ({route['skill_name']}) handoff needs "
                                f"deliverable(s) {missing} that are not in the certified package"))
        supporting: List[Dict[str, str]] = []
        for base in route.get("supporting", []):
            hit = by_base.get(base)
            if hit is not None:
                supporting.append({"deliverable": base, "file": hit["file"], "sha256": hit["sha256"]})
        targets.append({
            "skill_number": route["skill_number"],
            "skill_dir": route["skill_dir"],
            "skill_name": route["skill_name"],
            "purpose": route["purpose"],
            "inputs": inputs,
            "supporting": supporting,
        })

    if violations:
        return None, violations

    handoff = {
        "handoff": "avatar-alchemist-downstream",
        "skill": "52-avatar-alchemist",
        "client_label": client_label,
        "source_manifest_sha256": _sha256_bytes((deliver_dir / "MANIFEST.json").read_bytes()),
        "targets": targets,
        "notes": [BOOK_ROUTE_NOTE],
    }
    return handoff, []


def _render_md(handoff: Dict[str, Any]) -> str:
    label = handoff["client_label"].replace("_", " ")
    lines = [f"# Downstream Handoff — {label}", "",
             "Auto-generated by `aa_handoff.py` from the certified delivery package. Each downstream",
             "skill below consumes the listed deliverable file(s) as its next-step input.", ""]
    for t in handoff["targets"]:
        lines.append(f"## Skill {t['skill_number']} — {t['skill_name']}")
        lines.append(f"_{t['purpose']}_")
        lines.append("")
        for inp in t["inputs"]:
            lines.append(f"- [ ] `{inp['file']}`")
        for sup in t["supporting"]:
            lines.append(f"- [ ] `{sup['file']}` (supporting)")
        lines.append("")
    for note in handoff["notes"]:
        lines.append(f"> {note}")
    return "\n".join(lines) + "\n"


def write_handoff(deliver_dir: Path, out_dir: Path, *, require_cert: bool = True
                  ) -> Tuple[List[Tuple[str, str]], Optional[Dict[str, Any]]]:
    violations: List[Tuple[str, str]] = []
    if require_cert:
        violations += _require_certificate(deliver_dir)
    handoff, hv = build_handoff(deliver_dir)
    violations += hv
    if violations or handoff is None:
        return violations, None
    # bind the certificate bytes (when required/present) for traceability.
    cert_path = deliver_dir / CERT_NAME
    if cert_path.is_file():
        handoff["source_certificate_sha256"] = _sha256_bytes(cert_path.read_bytes())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "HANDOFF.json").write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    (out_dir / "HANDOFF.md").write_text(_render_md(handoff), encoding="utf-8")
    return [], handoff


# --- self-test ------------------------------------------------------------
_FIXTURE_BASES = [
    "AI_Bot_Prep_Doc_Intelligence", "AI_Booking_Bot_Intelligence",
    "AI_Post_Booking_Bot_Intelligence", "Rescheduling_Booking_Bot_Intelligence",
    "Top_39_Suggested_Ad_Angles", "Facebook_Headline_and_Primary_Text_Ad_Copy_Writer",
    "Facebook_Targeting_Intelligence", "Top_39_Suggested_Image_Prompts",
    "Landing_Page_Image_Prompts", "Landing_Page",
]


def _write_fixture(deliver_dir: Path, *, with_cert: bool = True,
                   drop_base: Optional[str] = None) -> None:
    deliver_dir.mkdir(parents=True, exist_ok=True)
    label = "Test_Fixture"
    files: Dict[str, Any] = {}
    for base in _FIXTURE_BASES:
        if base == drop_base:
            continue
        fn = f"{base}-{label}.md"
        body = f"# {base.replace('_', ' ')}\n\ncontent for {base}\n"
        (deliver_dir / fn).write_text(body, encoding="utf-8")
        files[fn] = {"sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                     "words": len(body.split())}
    (deliver_dir / "MANIFEST.json").write_text(
        json.dumps({"package": "avatar-alchemist-brand-intelligence",
                    "client_label": label, "deliverable_count": len(files),
                    "files": files}, indent=2), encoding="utf-8")
    if with_cert:
        (deliver_dir / CERT_NAME).write_text(
            json.dumps({"certificate": CERT_KIND, "skill": "52-avatar-alchemist",
                        "run_id": "selftest-run", "signature": "0" * 64}), encoding="utf-8")


def run_self_test() -> int:
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        # (1) a complete, certified package -> handoff written, 4 targets, all
        #     required inputs resolved with their manifest sha256.
        d = Path(td) / "ok"
        _write_fixture(d)
        vio, handoff = write_handoff(d, d)
        if vio or handoff is None:
            ok = False; print(f"SELF-TEST FAIL: valid package -> violations={vio}")
        elif len(handoff["targets"]) != len(HANDOFF_ROUTES):
            ok = False; print(f"SELF-TEST FAIL: expected {len(HANDOFF_ROUTES)} targets, got {len(handoff['targets'])}")
        elif not (d / "HANDOFF.json").is_file() or not (d / "HANDOFF.md").is_file():
            ok = False; print("SELF-TEST FAIL: HANDOFF.json / HANDOFF.md not written")
        else:
            reqs_ok = all(t["inputs"] and all(i["sha256"] for i in t["inputs"]) for t in handoff["targets"])
            if not reqs_ok:
                ok = False; print("SELF-TEST FAIL: a target has no resolved/sha256-bound required input")
            elif "source_certificate_sha256" not in handoff:
                ok = False; print("SELF-TEST FAIL: certified handoff missing source_certificate_sha256")
            else:
                print(f"SELF-TEST ok: complete certified package -> {len(handoff['targets'])} handoff targets, "
                      f"every required input resolved + sha256-bound.")

        # (2) deterministic: same package hashes to identical HANDOFF.json bytes.
        d2 = Path(td) / "ok2"
        _write_fixture(d2)
        write_handoff(d2, d2)
        h1 = json.loads((d / "HANDOFF.json").read_text())
        h2 = json.loads((d2 / "HANDOFF.json").read_text())
        h1.pop("source_manifest_sha256", None); h1.pop("source_certificate_sha256", None)
        h2.pop("source_manifest_sha256", None); h2.pop("source_certificate_sha256", None)
        if h1 == h2:
            print("SELF-TEST ok: routing body is deterministic (no wall-clock field).")
        else:
            ok = False; print("SELF-TEST FAIL: routing body differs across identical packages")

        # (3) uncertified package -> refused, no artifact written.
        d3 = Path(td) / "uncert"
        _write_fixture(d3, with_cert=False)
        vio, handoff = write_handoff(d3, d3)
        codes = {c for c, _ in vio}
        if "AF-AV-HANDOFF-UNCERTIFIED" in codes and handoff is None and not (d3 / "HANDOFF.json").is_file():
            print("SELF-TEST ok: uncertified package -> AF-AV-HANDOFF-UNCERTIFIED, no handoff written.")
        else:
            ok = False; print(f"SELF-TEST FAIL: uncertified package not refused -> {sorted(codes)}")

        # (4) incomplete package (a routed deliverable missing) -> fail closed.
        d4 = Path(td) / "incomplete"
        _write_fixture(d4, drop_base="Landing_Page")
        vio, handoff = write_handoff(d4, d4)
        codes = {c for c, _ in vio}
        if "AF-AV-HANDOFF-INCOMPLETE" in codes and handoff is None and not (d4 / "HANDOFF.json").is_file():
            print("SELF-TEST ok: incomplete package (missing Landing_Page) -> AF-AV-HANDOFF-INCOMPLETE, no handoff.")
        else:
            ok = False; print(f"SELF-TEST FAIL: incomplete package not refused -> {sorted(codes)}")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def _report(violations: List[Tuple[str, str]], handoff: Optional[Dict[str, Any]], out_dir: Path) -> None:
    if not violations and handoff is not None:
        n = len(handoff["targets"])
        print(f"PASS: downstream handoff written -> {out_dir / 'HANDOFF.json'} ({n} next-step targets).")
        return
    print(f"FAIL: {len(violations)} handoff violation(s) — no HANDOFF artifact written.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist downstream-handoff manifest generator.")
    ap.add_argument("--deliver-dir", help="the certified delivery folder (contains MANIFEST.json + PROCESS-CERTIFICATE.json)")
    ap.add_argument("--out", help="where to write HANDOFF.json/HANDOFF.md (default: the delivery folder)")
    ap.add_argument("--allow-uncertified", action="store_true",
                     help="build a handoff even if no PROCESS-CERTIFICATE.json is present (NOT for delivery)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return run_self_test()
    if not args.deliver_dir:
        print("USAGE ERROR: pass --deliver-dir <certified delivery folder> (or --self-test).")
        return 3
    deliver_dir = Path(args.deliver_dir)
    if not deliver_dir.is_dir():
        print(f"USAGE/IO ERROR: not a directory: {deliver_dir}")
        return 3
    out_dir = Path(args.out) if args.out else deliver_dir
    try:
        violations, handoff = write_handoff(deliver_dir, out_dir, require_cert=not args.allow_uncertified)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return 3
    _report(violations, handoff, out_dir)
    return 0 if not violations else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
