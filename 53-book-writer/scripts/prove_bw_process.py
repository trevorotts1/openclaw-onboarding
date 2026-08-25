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
    "scripts/mc_board.py",
]

# hand-rolled external sender signatures (delivery is LOCAL-ONLY)
# The webhook pattern anchors on n8n route shapes (n8n host, /webhook[-test]/<id>
# trigger path) so the Command Center's legitimate internal references in
# mc_board.py (CC_WEBHOOK_SECRET, x-webhook-signature against the CC's
# COMMAND_CENTER_URL /api routes) do not false-trip.
_BYPASS_PATTERNS = {
    "Google Drive upload/copy": re.compile(r"googleapis\.com/drive|drive\.files\(|/files/[^ ]*/copy", re.I),
    "Slack post": re.compile(r"slack\.com/api|chat\.postMessage|hooks\.slack\.com", re.I),
    "Gmail/SMTP send": re.compile(r"\bsmtplib\b|gmail\.com/|/messages/send|smtp\.gmail", re.I),
    "n8n webhook": re.compile(
        r"n8n\.cloud|X-N8N-API-KEY"                       # n8n cloud host / API key
        r"|https?://[^\s\"']*n8n[^\s\"']*/webhook"        # self-hosted n8n host
        r"|/webhook(?:-test)?/[A-Za-z0-9]",               # n8n trigger path with an id
        re.I),
    "Airtable write": re.compile(r"api\.airtable\.com", re.I),
    "GHL call": re.compile(r"services\.leadconnectorhq\.com|rest\.gohighlevel\.com", re.I),
}
# every executable source shape the bypass scan reads — a smuggled sender does not
# have to live in a .py file.
_SCAN_GLOBS = ("*.py", "*.sh", "*.js", "*.ts", "*.mjs", "*.cjs", "*.rb", "Makefile")

# Pin framing version. v2 length-prefixes each file's name and byte length before its
# bytes, so concatenation is unambiguous (v1 was delimiter-free h.update(data), which
# collides across file boundaries). A pin file carrying the v2 header is checked with
# this framing; a bare-hex pin keeps the legacy framing until re-minted.
PIN_FRAMING_V2 = "framing: v2\n"


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
    """sources: {relpath: text} for every executable source under the run dir.
    Identity is by RESOLVED PATH only — the real skill dir is excluded upstream by
    path (_run_dir_sources), never by basename, so a file named like an enforcement
    script gets the same scrutiny as any other."""
    r = c.Result("prove_bw_process:bypass-scan")
    for rel, src in sources.items():
        for why, pat in _BYPASS_PATTERNS.items():
            if pat.search(src):
                r.fail(AF_ENTRY_BYPASS, "%s: a %s (delivery is LOCAL-ONLY; no external senders)"
                       % (rel, why))
                break
    if r.passed:
        r.note("no hand-rolled external uploader/notifier in the run dir")
    return r


def _framed_digest(files) -> str:
    """Length-prefixed framing (v2): each file contributes 'name:len\\n' then its
    bytes — unambiguous across file boundaries, unlike bare concatenation."""
    h = hashlib.sha256()
    for name, data in files:
        h.update(("%s:%d\n" % (name, len(data))).encode("utf-8"))
        h.update(data)
    return h.hexdigest()


def version_hash_pin(files, pin) -> c.Result:
    """files: list of (name, bytes). pin: expected combined sha256 header+hex, or None.

    Framing: a pin file whose FIRST LINE is the v2 marker (framing: v2) is checked with
    length-prefixed framing; a bare-hex pin keeps the legacy delimiter-free framing.
    NOTE: the legacy framing is ambiguous across file boundaries and the committed
    ENGINE-PIN.sha256 still uses it — whoever owns install.sh's mint_pin must re-mint
    the committed pin under v2 framing before flipping the default.

    SK2-09: a MISSING pin is now a FAIL, not an advisory note. The ENGINE-PIN.sha256
    must be shipped/committed with the skill; without it the enforcement-set hash is
    UNPINNED and a modified orchestrator/prover could pass silently (the pin gate is
    the AF-BK-HASH-PIN teeth). book-writer-entry.sh mints the pin at install if
    absent, and it is committed in the repo, so a genuine install always has it."""
    r = c.Result("prove_bw_process:hash-pin")
    computed_v2 = _framed_digest(files)
    computed_v1 = hashlib.sha256(b"".join(data for _n, data in files)).hexdigest()
    if pin is None:
        r.fail(AF_HASH_PIN, "no ENGINE-PIN.sha256 present — the enforcement-set hash (%s..) is "
               "UNPINNED; fail-closed (the pin must be committed/minted so a modified prover or "
               "orchestrator cannot pass silently)" % computed_v2[:12])
        return r
    text = pin.strip()
    if text.startswith(PIN_FRAMING_V2.strip()):
        expected = text.split("\n", 1)[1].strip()
        computed = computed_v2
        framing = "v2"
    else:
        expected = text
        computed = computed_v1
        framing = "v1"
    if expected != computed:
        r.fail(AF_HASH_PIN, "enforcement-set hash %s (%s framing).. != pinned head %s.. "
               "(a prover was modified)" % (computed[:12], framing, expected[:12]))
    else:
        r.note("enforcement-set hash matches the pinned head (%s framing, %s..)"
               % (framing, computed[:12]))
    return r


# ---- CLI wrappers -----------------------------------------------------------
def _load_cert_steps(path):
    obj = c.read_json(path)
    return obj.get("steps", [])


def _run_dir_sources(run_dir: str, skill_dir) -> dict:
    out = {}
    rd = Path(run_dir).resolve()
    sd = Path(skill_dir).resolve() if skill_dir else None
    seen = set()
    for pattern in _SCAN_GLOBS:
        for p in rd.rglob(pattern):
            rp = p.resolve()
            if str(rp) in seen or not p.is_file():
                continue
            seen.add(str(rp))
            if sd and (str(rp).startswith(str(sd) + os.sep) or rp == sd):
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


def prove_run(run_dir, skill_dir=None, as_json=False) -> int:
    # the pin check is NEVER optional: with no --skill-dir given we default to this
    # prover's own skill root, so omitting the flag still verifies the hash pin.
    if skill_dir is None:
        skill_dir = Path(__file__).resolve().parents[1]
    r = c.Result("prove_bw_process")
    scan = bypass_scan(_run_dir_sources(run_dir, skill_dir))
    r.violations += scan.violations
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
    # a file NAMED like an enforcement script gets no basename exemption: a Slack
    # webhook inside it must still trip the bypass scan.
    checks.append(("Slack webhook inside an enforcement-SCRIPT-NAMED file AUTOFAILs "
                   "AF-BK-ENTRY-BYPASS",
                   any(cd == AF_ENTRY_BYPASS for cd, _ in bypass_scan(
                       {"scripts/prove_bw_noanthropic.py":
                        'send("https://hooks.slack.com/services/T000/B000/XXXX")'}).violations)))
    # non-.py executable shapes are scanned too (the *.py-only gap)
    checks.append(("a .sh uploader AUTOFAILs AF-BK-ENTRY-BYPASS",
                   any(cd == AF_ENTRY_BYPASS for cd, _ in
                       bypass_scan({"upload.sh": "curl https://www.googleapis.com/drive/v3/files -d @f"}).violations)))
    checks.append(("a Makefile n8n webhook AUTOFAILs AF-BK-ENTRY-BYPASS",
                   any(cd == AF_ENTRY_BYPASS for cd, _ in
                       bypass_scan({"Makefile": "push:\n\tcurl -X POST https://example.n8n.cloud/webhook/x"}).violations)))
    # the anchored webhook pattern: an n8n-style trigger URL still trips ...
    checks.append(("an n8n-style /webhook/<id> URL AUTOFAILs AF-BK-ENTRY-BYPASS",
                   any(cd == AF_ENTRY_BYPASS for cd, _ in
                       bypass_scan({"flow.py": "requests.post('https://n8n.internal/webhook/abc123', json=d)"}).violations)))
    checks.append(("an n8n -test trigger path AUTOFAILs AF-BK-ENTRY-BYPASS",
                   any(cd == AF_ENTRY_BYPASS for cd, _ in
                       bypass_scan({"t.py": "url = 'https://host.example/webhook-test/9f2e'"}).violations)))
    # ... while the Command Center's legitimate internal references do NOT
    checks.append(("Command Center x-webhook-signature / CC_WEBHOOK_SECRET references PASS "
                   "(no false trip)",
                   bypass_scan({"scripts/mc_board.py":
                                'headers["x-webhook-signature"] = sig\n'
                                'secret = env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET")\n'
                                'url = f"{cfg[\'base_url\']}/api/tasks/ingest"'}).passed))
    files = [("a", b"x"), ("b", b"y")]
    checks.append(("MISSING pin AUTOFAILs AF-BK-HASH-PIN (SK2-09 fail-closed)",
                   any(cd == AF_HASH_PIN for cd, _ in version_hash_pin(files, None).violations)))
    checks.append(("wrong pin AUTOFAILs AF-BK-HASH-PIN",
                   any(cd == AF_HASH_PIN for cd, _ in version_hash_pin(files, "deadbeef").violations)))
    _good_pin = hashlib.sha256(b"xy").hexdigest()
    checks.append(("matching pin (v1 framing) PASSES", version_hash_pin(files, _good_pin).passed))
    _good_pin_v2 = _framed_digest(files)
    checks.append(("matching pin (v2 framing) PASSES",
                   version_hash_pin(files, PIN_FRAMING_V2 + _good_pin_v2).passed))
    checks.append(("v2-flagged pin with v1 hash AUTOFAILs AF-BK-HASH-PIN (framing collision)",
                   any(cd == AF_HASH_PIN for cd, _ in
                       version_hash_pin(files, PIN_FRAMING_V2 + _good_pin).violations)))
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
