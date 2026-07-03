#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: PROCESS-GUARD GATE (fail-closed)
# -----------------------------------------------------------------------------
# The process teeth that mirror Skill 55's entry + orchestrator guards:
#
#   AF-BK-STAGE-SKIPPED     — a phase was attempted out of order / a phase missing
#                             from the certificate's ordered step chain.
#   AF-BK-PROCESS-INTEGRITY — a certificate was requested/emitted without a full
#                             P0->P7 pass (all steps ok).
#   AF-BK-HASH-PIN          — the enforcement-set hash (orchestrator + provers +
#                             _bw_common) != the pinned head (ENGINE-PIN.sha256).
#   AF-BK-ENTRY-BYPASS      — a hand-rolled external uploader/notifier (Drive /
#                             Slack / Gmail / n8n / Airtable / GHL) is present in the
#                             run dir, bypassing the local-only delivery.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE:
#   prove_bw_process.py --certificate <PROCESS-CERTIFICATE.json> [--json]
#   prove_bw_process.py --run-dir DIR [--skill-dir DIR] [--json]
#   prove_bw_process.py --self-test
# =============================================================================
"""Fail-closed Book Writer process-guard gate (Skill 53)."""

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_STAGE_SKIPPED = "AF-BK-STAGE-SKIPPED"
AF_PROCESS_INTEGRITY = "AF-BK-PROCESS-INTEGRITY"
AF_HASH_PIN = "AF-BK-HASH-PIN"
AF_ENTRY_BYPASS = "AF-BK-ENTRY-BYPASS"

PHASE_ORDER = ["P0-INTAKE", "P1-AVATAR", "P2-TONE", "P3-TITLES-GATE", "P4-OUTLINE-GATE",
               "P5-CHAPTERS", "P6-PACKAGE", "P7-QC", "P8-DELIVER"]

# the enforcement set whose combined sha256 is pinned in ENGINE-PIN.sha256
ENFORCE_FILES = [
    "run_book_writer.py", "scripts/_bw_common.py",
    "scripts/prove_bw_intake.py", "scripts/prove_bw_titlelock.py",
    "scripts/prove_bw_stories.py", "scripts/prove_bw_chapters.py",
    "scripts/prove_bw_continuity.py", "scripts/prove_bw_tone.py",
    "scripts/prove_bw_challenge.py", "scripts/prove_bw_433.py",
    "scripts/prove_bw_placeholder.py", "scripts/prove_bw_noanthropic.py",
    "scripts/prove_bw_anon.py", "scripts/prove_bw_process.py",
]

# hand-rolled external sender signatures (delivery is LOCAL-ONLY)
_BYPASS_PATTERNS = {
    "Google Drive upload/copy": re.compile(r"googleapis\.com/drive|drive\.files\(|/files/[^ ]*/copy", re.I),
    "Slack post": re.compile(r"slack\.com/api|chat\.postMessage|hooks\.slack\.com", re.I),
    "Gmail/SMTP send": re.compile(r"\bsmtplib\b|gmail\.com/|/messages/send|smtp\.gmail", re.I),
    "n8n webhook": re.compile(r"/webhook/|n8n\.cloud|X-N8N-API-KEY", re.I),
    "Airtable write": re.compile(r"api\.airtable\.com", re.I),
    "GHL call": re.compile(r"services\.leadconnectorhq\.com|rest\.gohighlevel\.com", re.I),
}
_CANON = {Path(f).name for f in ENFORCE_FILES}


def check_stage_chain(steps) -> c.Result:
    """steps: list of {phase_id, ok} in declared order."""
    r = c.Result("prove_bw_process:stage-chain")
    ids = [s.get("phase_id") for s in steps]
    if ids != PHASE_ORDER:
        r.fail(AF_STAGE_SKIPPED, "certificate phase chain %s != canonical order %s "
               "(phase skipped or reordered)" % (ids, PHASE_ORDER))
    all_ok = all(s.get("ok") for s in steps) and len(steps) == len(PHASE_ORDER)
    if not all_ok:
        r.fail(AF_PROCESS_INTEGRITY, "certificate present without a full P0->P8 pass "
               "(a phase step is not ok)")
    if r.passed:
        r.note("phase chain complete and in order; all phases ok")
    return r


def bypass_scan(sources: dict) -> c.Result:
    """sources: {relpath: text} for .py files in the run dir (canonical skill files excluded)."""
    r = c.Result("prove_bw_process:bypass-scan")
    for rel, src in sources.items():
        name = Path(rel).name
        if name in _CANON:
            continue
        for why, pat in _BYPASS_PATTERNS.items():
            if pat.search(src):
                r.fail(AF_ENTRY_BYPASS, "%s: a %s (delivery is LOCAL-ONLY; no external senders)"
                       % (rel, why))
                break
    if r.passed:
        r.note("no hand-rolled external uploader/notifier in the run dir")
    return r


def version_hash_pin(files, pin) -> c.Result:
    """files: list of (name, bytes). pin: expected combined sha256 or None."""
    r = c.Result("prove_bw_process:hash-pin")
    h = hashlib.sha256()
    for _name, data in files:
        h.update(data)
    computed = h.hexdigest()
    if pin is None:
        r.note("no ENGINE-PIN.sha256 recorded; enforcement hash computed (%s..) not enforced"
               % computed[:12])
    elif pin.strip() != computed:
        r.fail(AF_HASH_PIN, "enforcement-set hash %s.. != pinned head %s.. (a prover was modified)"
               % (computed[:12], pin.strip()[:12]))
    else:
        r.note("enforcement-set hash matches the pinned head (%s..)" % computed[:12])
    return r


# ---- CLI wrappers -----------------------------------------------------------
def _load_cert_steps(path):
    obj = c.read_json(path)
    return obj.get("steps", [])


def _run_dir_sources(run_dir: str, skill_dir: str) -> dict:
    out = {}
    rd = Path(run_dir).resolve()
    sd = Path(skill_dir).resolve() if skill_dir else None
    for p in rd.rglob("*.py"):
        rp = p.resolve()
        if sd and str(rp).startswith(str(sd) + os.sep):
            continue
        try:
            out[str(p.relative_to(rd))] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return out


def _enforce_files_bytes(skill_dir: str):
    files = []
    for rel in ENFORCE_FILES:
        p = Path(skill_dir) / rel
        files.append((rel, p.read_bytes() if p.is_file() else b""))
    return files


def prove_run(run_dir, skill_dir, as_json=False) -> int:
    r = c.Result("prove_bw_process")
    scan = bypass_scan(_run_dir_sources(run_dir, skill_dir or ""))
    r.violations += scan.violations
    if skill_dir:
        pin_path = Path(skill_dir) / "ENGINE-PIN.sha256"
        pin = pin_path.read_text(encoding="utf-8") if pin_path.is_file() else None
        hp = version_hash_pin(_enforce_files_bytes(skill_dir), pin)
        r.violations += hp.violations
    return r.emit(as_json)


def prove_certificate(cert_path, as_json=False) -> int:
    return check_stage_chain(_load_cert_steps(cert_path)).emit(as_json)


def self_test() -> int:
    good_steps = [{"phase_id": p, "ok": True} for p in PHASE_ORDER]
    checks = []
    checks.append(("full ordered passing chain PASSES", check_stage_chain(good_steps).passed))
    reordered = [{"phase_id": p, "ok": True} for p in
                 ["P0-INTAKE", "P2-TONE", "P1-AVATAR", "P3-TITLES-GATE", "P4-OUTLINE-GATE",
                  "P5-CHAPTERS", "P6-PACKAGE", "P7-QC", "P8-DELIVER"]]
    checks.append(("reordered chain AUTOFAILs AF-BK-STAGE-SKIPPED",
                   any(cd == AF_STAGE_SKIPPED for cd, _ in check_stage_chain(reordered).violations)))
    failed = [{"phase_id": p, "ok": (p != "P5-CHAPTERS")} for p in PHASE_ORDER]
    checks.append(("certificate with a failed phase AUTOFAILs AF-BK-PROCESS-INTEGRITY",
                   any(cd == AF_PROCESS_INTEGRITY for cd, _ in check_stage_chain(failed).violations)))
    checks.append(("clean run dir PASSES bypass-scan",
                   bypass_scan({"note.py": "print('local only')"}).passed))
    checks.append(("a Drive uploader AUTOFAILs AF-BK-ENTRY-BYPASS",
                   any(cd == AF_ENTRY_BYPASS for cd, _ in
                       bypass_scan({"up.py": "requests.post('https://www.googleapis.com/drive/v3/files')"}).violations)))
    checks.append(("a GHL caller AUTOFAILs AF-BK-ENTRY-BYPASS",
                   any(cd == AF_ENTRY_BYPASS for cd, _ in
                       bypass_scan({"ghl.py": "requests.get('https://services.leadconnectorhq.com/x')"}).violations)))
    files = [("a", b"x"), ("b", b"y")]
    checks.append(("no pin -> note only, PASS", version_hash_pin(files, None).passed))
    checks.append(("wrong pin AUTOFAILs AF-BK-HASH-PIN",
                   any(cd == AF_HASH_PIN for cd, _ in version_hash_pin(files, "deadbeef").violations)))
    return c.selftest_report("prove_bw_process", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer process-guard gate (Skill 53).")
    ap.add_argument("--certificate", help="PROCESS-CERTIFICATE.json to check the phase chain")
    ap.add_argument("--run-dir", help="run dir to bypass-scan")
    ap.add_argument("--skill-dir", help="skill dir for the enforcement hash pin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.certificate:
        return prove_certificate(args.certificate, as_json=args.json)
    if args.run_dir:
        return prove_run(args.run_dir, args.skill_dir, as_json=args.json)
    ap.error("--certificate or --run-dir required (or use --self-test)")


if __name__ == "__main__":
    sys.exit(main())
