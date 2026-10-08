"""H12: the master must come from the skill's assembler, never a hand-written script.

check_master_provenance(run_dir, master) passes only when
  1. <master>.receipt.json exists, is outcome ok, and names a skill module
     in produced_by.module;
  2. the receipt's master_sha256 equals the sha256 of the master file
     (a master swapped in after assembly has no receipt that matches);
  3. no run-folder script (.py .sh .bash .zsh .js .mjs) drives ffmpeg or
     writes captions itself (lip-sync clips are placed by ffmpeg, so the
     ffmpeg pattern covers hand-written lip-sync placement too).
Stdlib only, no ffmpeg needed. ponytail: pattern scan, not a parser; a
script that hides the word ffmpeg (base64, getattr) gets past rule 3 but
still fails rule 1 or 2 because the receipt hash will not match.
"""
import hashlib
import json
import os
import re

TOOL_VERSION = "1.0.0"
CHECK = "final_edit"
NON_SKILL_SCRIPT = "NON_SKILL_SCRIPT"
RECEIPT_MISSING = "RECEIPT_MISSING"
NOT_SKILL_MODULE = "MASTER_NOT_FROM_SKILL_MODULE"
MASTER_HASH_MISMATCH = "MASTER_HASH_MISMATCH"

# Modules allowed to produce a master (receipt produced_by.module).
SKILL_MODULES = frozenset({"final_assembler.assembler"})
SCRIPT_EXT = (".py", ".sh", ".bash", ".zsh", ".js", ".mjs")
# ffmpeg/ffprobe calls, caption writers (.srt/.ass/vtt, drawtext, subtitles=).
_HAND_RE = re.compile(
    r"\bffmpeg\b|\bffprobe\b|drawtext|subtitles=|WEBVTT|\.srt\b|\.ass\b",
    re.I)


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def producer_stamp():
    """The produced_by block the assembler writes into every ok receipt."""
    return {"module": "final_assembler.assembler",
            "skill": "drama-song-ad-factory"}


def scan_run_scripts(run_dir):
    """Run-folder scripts that do assembly/caption work themselves."""
    bad = []
    for root, dirs, files in os.walk(run_dir):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for name in files:
            if not name.lower().endswith(SCRIPT_EXT):
                continue
            p = os.path.join(root, name)
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    if _HAND_RE.search(fh.read()):
                        bad.append(os.path.relpath(p, run_dir))
            except OSError as exc:
                _loud("fail", "HAND_WRITTEN_SCAN_UNREADABLE",
                      "%s could not be scanned: %r" % (p, exc))
                continue
    return sorted(bad)


def _res(ok, code, summary, **ev):
    ev["summary"] = summary
    return {"pass": ok, "reason_code": code, "evidence": ev}


def check_master_provenance(run_dir, master):
    scripts = scan_run_scripts(run_dir)
    if scripts:
        return _res(False, NON_SKILL_SCRIPT,
                    "hand-written script(s) in run folder: %s"
                    % ", ".join(scripts), scripts=scripts)
    try:
        with open(str(master) + ".receipt.json", encoding="utf-8") as fh:
            rc = json.load(fh)
    except (OSError, ValueError):
        return _res(False, RECEIPT_MISSING,
                    "no readable assembler receipt for the master")
    mod = (rc.get("produced_by") or {}).get("module") \
        if isinstance(rc, dict) else None
    if rc.get("outcome") != "ok" or mod not in SKILL_MODULES:
        return _res(False, NOT_SKILL_MODULE,
                    "receipt does not name a skill module (got %r)" % (mod,),
                    module=mod)
    try:
        actual = sha256_file(master)
    except OSError:
        return _res(False, RECEIPT_MISSING, "master file unreadable")
    if rc.get("master_sha256") != actual:
        return _res(False, MASTER_HASH_MISMATCH,
                    "master does not match the receipt hash", module=mod)
    return _res(True, "OK", "master produced by %s" % mod, module=mod)


def to_qc_record(result, run_id, stage, reviewer, check_id="master-provenance"):
    """qc-schema 1.0.0 record (check=final_edit); qc_gate enforces independence."""
    for k in ("identity", "session", "authority"):
        if not reviewer.get(k):
            raise ValueError("reviewer.%s is required" % k)
    ok = bool(result["pass"])
    return {"schema_version": "1.0.0", "check_id": check_id, "run_id": run_id,
            "stage": stage, "check": CHECK,
            "verdict": "PASS" if ok else "FAIL",
            "evidence": {"summary": result["evidence"]["summary"][:300],
                         "refs": ["Part H H12"]},
            "checker_version": TOOL_VERSION, "reviewer": dict(reviewer)}
