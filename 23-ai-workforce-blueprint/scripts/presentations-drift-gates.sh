#!/usr/bin/env bash
# FIX 45: CANONICAL-ENTRY COPY of presentations-drift-gates.sh -- called by name by presentation-canonical-entry.sh (Fix 53); the twin copy at the other 23-ai-workforce-blueprint presentations/scripts/ path must stay byte-identical to this one (Fix 52); the third same-named copy is the CI one at scripts/ci/. Do not rename any of them.
# presentations-drift-gates.sh — FIX 113: REPO / DEPARTMENT / PROVENANCE-STAMP
# three-way drift gate, run at the canonical entry BEFORE every build.
#
# THE BROKEN STATE (measured 2026-09-02, operator box): the materialized
# department's build_deck.py had drifted from the repo role-library copy
# (sha 4289c18e… vs 161f5cc9…), the department sops/PIPELINE-MANIFEST.json sat
# at manifest_version 54 while the repo copy was 59, and the department's
# sops/MANIFEST-SOURCE.txt recorded the sha of the STALE bytes — internally
# consistent, so every per-copy provenance check passed on both copies while
# the two copies disagreed. Dispatch runs the department copy; a repo-only fix
# was invisible to the run. This class has now bitten twice (FIX 32 measured
# it 2026-08-31; it was live again 2026-09-02).
#
# WHAT THIS GATE DOES (fail-closed, exit 11, names the differing file):
# compares the content sha256 of
#   (1) the repo role-library copy    (the canonical source),
#   (2) the materialized department copy (what dispatch actually runs)
# for every canonical-suffix file in the department scripts/ tree, plus the
# provenance stamp: sops/MANIFEST-SOURCE.txt's content_sha256 must equal the
# department manifest's sha (no stale stamp masquerading as provenance) and
# the manifest CONTENT must match the repo copy (no repo-only fix running
# invisible). A stale stamp is indistinguishable from tampering, so it fails
# the same way, and the message names the sanctioned repair: run the
# reinstall/update roll, which re-mirrors via refresh-dept-scripts.py and
# restamps via restamp_manifest_source (FIX 113) — then the door opens.
#
# COMPARISON SEMANTICS: byte-level sha256, per file. One edited byte (the FIX
# 113 proof) is caught; nothing slips past a hash.
#
# BOX-OWNED ALLOWLIST (FIX 66 policy, same as verify_dept_scripts_stamp):
# .json files under scripts/ are client-local overrides — copied missing-only
# by every writer, never hash-enforced here. The intake/ tree is NOT this
# gate's scope (the door does not dispatch from it; refresh-dept-intake.py
# owns it). The sops/ tree is covered ONLY through the manifest + stamp legs
# below — SOP prose is not byte-pinned anywhere and must not start being.
#
# EXIT CODES
#   0  — every compared file identical; stamp matches the department manifest;
#        manifest content matches the repo copy
#   11 — drift found (each differing file named, with both shas)
#   2  — environment error (a copy missing entirely / unresolved repo tree):
#        fail-closed, never a pass the gate could not actually perform
#
# When called by the entry door (GATE 0c) a non-zero exit is logged as a
# WARNING and the build continues (owner ruling D6). When called by continuous
# integration a non-zero exit fails the job.
#
# PRESENTATION_DRIFT_GATE=0 documents the skip everywhere it is honored: the
# disabled path PRINTS the skip and exits 0 — it never reports a pass it did
# not perform. Default (unset or =1) is ON.
#
# RESOLUTION — this file ships as BYTE-IDENTICAL GENERATED MIRRORS in both
# trees (same rule as presentation-canonical-entry.sh: edit the role-library
# copy, re-mirror). Whichever copy runs, BOTH sides are resolved explicitly:
#   dept copy = $OPENCLAW_WORKSPACE/departments/Presentations/scripts
#               (default ~/.openclaw/workspace, /data/.openclaw/workspace on
#               the VPS layout)
#   repo copy = walk up from this file for the 23-ai-workforce-blueprint
#               checkout; else the repo clone at ~/openclaw-onboarding; else
#               the skills cluster copy. Order matters: the checkout is the
#               source of truth (GitHub truth), the skills cluster is what an
#               old install left behind. A repo tree that cannot be resolved
#               fails the gate (exit 2) — an unverifiable door must not open.

set -uo pipefail

PROG="presentations-drift-gates.sh"

die() { echo "FATAL [$PROG]: $*" >&2; exit 2; }

FLAG="${PRESENTATION_DRIFT_GATE:-1}"
if [ "$FLAG" = "0" ]; then
    echo "=== [$PROG] SKIPPED: PRESENTATION_DRIFT_GATE=0 — repo/department/provenance comparison DISABLED by rollback flag; the department copy is UNVERIFIED for this run ==="
    exit 0
fi

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Resolve the DEPARTMENT copy.
# ---------------------------------------------------------------------------
OC_WORKSPACE="${OPENCLAW_WORKSPACE:-}"
if [ -z "$OC_WORKSPACE" ]; then
    if [ -d "/data/.openclaw/workspace/departments" ]; then
        OC_WORKSPACE="/data/.openclaw/workspace"
    else
        OC_WORKSPACE="$HOME/.openclaw/workspace"
    fi
fi
DEPT_SCRIPTS="$OC_WORKSPACE/departments/Presentations/scripts"
DEPT_SOPS="$OC_WORKSPACE/departments/Presentations/sops"
DEPT_MANIFEST="$DEPT_SOPS/PIPELINE-MANIFEST.json"
[ -f "$DEPT_MANIFEST" ] || die "department manifest not found at $DEPT_MANIFEST — the Presentations department is not materialized; there is no department copy to verify. Materialize the department first."

# ---------------------------------------------------------------------------
# Resolve the REPO copy.
# ---------------------------------------------------------------------------
find_repo_scripts() {
    local cand cur
    cur="$SELF_DIR"
    while :; do
        cand="$cur/23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
        if [ -d "$cand" ] && [ -f "$cand/build_deck.py" ]; then
            (cd "$cand" && pwd); return 0
        fi
        [ "$cur" = "/" ] && break
        cur="$(dirname "$cur")"
    done
    for cand in "$HOME/openclaw-onboarding/23-ai-workforce-blueprint/templates/role-library/presentations/scripts" \
                "$HOME/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/presentations/scripts" \
                "/data/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/presentations/scripts"; do
        if [ -d "$cand" ] && [ -f "$cand/build_deck.py" ]; then
            (cd "$cand" && pwd); return 0
        fi
    done
    return 1
}
REPO_SCRIPTS="$(find_repo_scripts)" || {
    die "cannot resolve the repo role-library copy (walked up from $SELF_DIR, then tried ~/openclaw-onboarding and the skills cluster). A drift gate that cannot see the canonical source must fail closed, never pass. Install the 23-ai-workforce-blueprint bundle."
}
REPO_MANIFEST="$REPO_SCRIPTS/../../../../universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"
if [ ! -f "$REPO_MANIFEST" ]; then
    for cand in "$HOME/openclaw-onboarding/universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json" \
                "$HOME/.openclaw/skills/universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json" \
                "/data/.openclaw/skills/universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"; do
        if [ -f "$cand" ]; then REPO_MANIFEST="$cand"; break; fi
    done
fi
[ -f "$REPO_MANIFEST" ] || die "repo PIPELINE-MANIFEST.json not found (tried $REPO_SCRIPTS/../../../../universal-sops/..., ~/openclaw-onboarding, the skills cluster)."
DEPT_STAMP="$DEPT_SOPS/MANIFEST-SOURCE.txt"

sha() { # sha256 of a file, portable
    if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
    else die "no sha256 tool available (need shasum or sha256sum)"; fi
}

DRIFT=0
fail() { echo "  DRIFT: $*" >&2; DRIFT=1; }

echo "=== [$PROG] GATE-D — repo/department/provenance drift (FIX 113) ==="
echo "  repo copy:  $REPO_SCRIPTS"
echo "  dept copy:  $DEPT_SCRIPTS"

# ---------------------------------------------------------------------------
# LEG 1 + 2 — scripts/ tree, file by file. Every canonical-suffix file the REPO
# ships must exist in the DEPARTMENT copy with the same sha256 (LEG 1: a
# repo-only fix is invisible until mirrored), and every canonical-suffix file
# in the DEPARTMENT tree the repo does NOT ship is named as a stray (LEG 2: it
# shadows the canonical file the next fix would deliver). Scope notes that keep
# both legs exact instead of noisy:
#   * .json is box-owned (FIX 66 allowlist) and never enforced either way;
#     .md and .pdf are EXCLUDED from the stray leg only — older installs
#     materialized the whole department (IDENTITY.md, SOP prose, agent docs)
#     INTO the scripts dir, so dept-root .md/.pdf files are box layout, not
#     renderer strays; a repo-shipped .md/.pdf is still hash-enforced (LEG 1).
#   * Hidden dirs, caches, .pyc and .DS_Store are pruned on BOTH sides; *.bak*
#     files are rollback material on both sides and never canonical.
#
# FIX 113 (B2 correction, proven live on the operator box): LEG 2 strays are
# REPORTED LOUDLY but do NOT fail the gate. The sanctioned repair
# (refresh-dept-scripts.py) is deliberately ADDITIVE — it mirrors repo files in
# and never deletes box files — so a hard-failing stray leg names files the
# named repair can never remove: the door stayed shut after a clean re-mirror
# (measured: mc_task.py, qc-completeness.sh, prove_sp_routing.py,
# tests/test_engine_deck_shape_routing.py — box-local utilities and prover
# scripts from earlier fixes, present on an otherwise healthy box). A stray
# CANNOT silently shadow a canonical file the moment the repo ships a file of
# the same name: that rel path becomes a LEG 1 hash mismatch, which still fails
# the gate. So the shadowing hazard LEG 2 guards is fully covered by LEG 1;
# the stray list stays visible for hygiene, exit stays 0 when ONLY strays
# differ.
# ---------------------------------------------------------------------------
python3 - "$REPO_SCRIPTS" "$DEPT_SCRIPTS" <<'PYGATE' || DRIFT=1
import hashlib
import os
import re
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
dept_root = Path(sys.argv[2]).resolve()
# Canonical, hash-enforced on BOTH legs:
CANON = re.compile(r"\.(py|sh|js|tpl|sha256|template)$")
# Repo-shipped but hash-enforced on LEG 1 only (see stray-leg scope note):
CANON_REPO_DOC = re.compile(r"\.(md|pdf)$")
PRUNE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".git"}

def is_bak(name):
    return ".bak" in name

def walk(root):
    out = {}
    for cur, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs
                         if d not in PRUNE_DIRS and not d.startswith("."))
        for fn in sorted(files):
            if fn == ".DS_Store" or fn.endswith(".pyc") or is_bak(fn):
                continue
            p = Path(cur) / fn
            rel = p.relative_to(root).as_posix()
            out[rel] = p
    return out

import os
repo_files = walk(repo_root)
dept_files = walk(dept_root)

def sha(p):
    # A file can vanish between the walk and the hash (a concurrent mirror or
    # cleanup). Unreadable-at-hash-time == not verifiable == MISSING, never a
    # crash: the gate must always emit a verdict, never a traceback.
    try:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None

problems = []
strays = []
leg1_count = 0
for rel, rp in sorted(repo_files.items()):
    if not (CANON.search(rel) or CANON_REPO_DOC.search(rel)):
        continue  # not a hash-enforced repo asset (json = box-owned, etc.)
    leg1_count += 1
    dp = dept_root / rel
    a = sha(rp)
    b = sha(dp) if dp.is_file() else None
    if b is None:
        problems.append(
            f"{rel} — MISSING from the department copy (repo sha256={a[:16]}…); "
            f"a repo-only fix is not on this box until the department is re-mirrored")
        continue
    if a != b:
        problems.append(
            f"{rel} — repo sha256={a[:16]}… vs department sha256={b[:16]}… "
            f"(one differs; the department copy is not the repo bytes)")
for rel, dp in sorted(dept_files.items()):
    if not CANON.search(rel):
        continue  # .md/.pdf/.json dept-root files are box layout, not strays
    if rel not in repo_files:
        dsha = sha(dp) or "unreadable"
        strays.append(
            f"{rel} — STRAY in the department copy, not shipped by the repo "
            f"(department sha256={dsha[:16]}…); box-local file, NOT repaired by the "
            f"mirror (additive). It shadows nothing while the repo ships no file of "
            f"the same name — the moment it does, LEG 1 hash mismatch fails the gate")

if problems:
    print(f"  SCRIPTS-TREE DRIFT: {len(problems)} file(s) differ between the repo copy and the "
          f"department copy (FIX 113):", file=sys.stderr)
    for p in problems:
        print(f"    - {p}", file=sys.stderr)
    print("  Repair: run the reinstall/update roll (refresh-dept-scripts.py re-mirrors the "
          "department from the repo), then re-run. Do NOT hand-edit the department copy.",
          file=sys.stderr)
    sys.exit(1)
if strays:
    # FIX 113 (B2): strays are a WARN, never a fail — see the LEG 2 note above.
    print(f"  NOTE: {len(strays)} box-local file(s) in the department copy that the repo does "
          f"not ship (strays, reported for hygiene, NOT drift — the additive mirror never "
          f"removes box files):", file=sys.stderr)
    for s in strays:
        print(f"    - {s}", file=sys.stderr)
print("  OK: every canonical scripts/ file matches the repo copy byte-for-byte "
      f"({leg1_count} repo-shipped files compared; .json is box-owned, .md/.pdf strays out of scope)")
sys.exit(0)
PYGATE

# ---------------------------------------------------------------------------
# LEG 3 — the provenance stamp. sops/MANIFEST-SOURCE.txt must exist and record
# the sha of the department manifest's CURRENT bytes (a stale stamp is
# indistinguishable from tampering — same failure). LEG 4 — the department
# manifest's CONTENT must equal the repo copy's (canonical-JSON, per FIX 32's
# content hashing: whitespace is not drift, values are).


# ---------------------------------------------------------------------------
# GATE 8 (FIX 61): A scheduled path creates jobs -- the intake poll must be
# WIRED, not merely present. The poll script and its launchd plist template
# are dead letters unless (a) install.sh carries the installer that renders
# the template into ~/Library/LaunchAgents/com.blackceo.presentation-intake-poll.plist
# (or registers an openclaw cron on Linux), and (b) that installer is
# CALLED from the main install flow. Without the call site a staged
# submission sits staged forever with no human action -- the exact QC.md
# FIX 61 failure. Asserted by text contracts for (2)/(3)/(5); clause (4) is a
# real definition-body parse since PD-009 (the old whole-file regex passed on
# the definition itself).
echo "== GATE 8: intake-poll schedule wiring (FIX 61) =="
GATE8_RC=0
# fix/r-f02-b3: the FIX 61 block referenced $REPO_ROOT/$SCRIPTS_DIR — variables this script never
# defines; under `set -u` every invocation died "REPO_ROOT: unbound" before reaching the drift
# comparison, bricking the door fleet-wide. The gate's own names are REPO_SCRIPTS + DEPT_SCRIPTS.
python3 - "$REPO_SCRIPTS" "$DEPT_SCRIPTS" <<'PYEOF' || GATE8_RC=$?
import re, sys
from pathlib import Path
repo = Path(sys.argv[1]); scr = sys.argv[2]
fails = []
tpl = repo / "presentation-intake-poll.plist.template"
poll = repo / "presentation-intake-poll.sh"
if not tpl.is_file():
    fails.append("(1) plist template missing: " + str(tpl))
if not poll.is_file():
    fails.append("(1) poll script missing: " + str(poll))
# install.sh lives at the REPO ROOT — five levels above the scripts dir
# (scripts -> presentations -> role-library -> templates -> 23-ai-workforce-
# blueprint -> repo root). The original `repo / "install.sh"` looked inside the
# scripts dir itself, found no file, and read "" — clauses (2)-(5) then fired on
# every tree forever (the gate could only ever FAIL, never pass, hiding real
# drift behind permanent noise). Measured 2026-09-04 on PR-fix/fix61.
inst = repo / "../../../../.." / "install.sh"
inst_text = inst.read_text(encoding="utf-8", errors="replace") if inst.is_file() else ""
if "install_intake_poll_schedule()" not in inst_text:
    fails.append("(2) install.sh does not define install_intake_poll_schedule() -- the scheduled path has no installer")
if "presentation-intake-poll.plist.template" not in inst_text:
    fails.append("(3) install.sh never resolves the intake-poll plist template -- the installer would always SKIP")
# PD-009: clause (4) used to be a regex over the WHOLE file, so the function
# DEFINITION itself matched and a defined-but-never-called installer passed.
# Parse the definition instead: the body runs from the header line (after
# optional whitespace) to the first line that is a bare `}` at column 0, and a
# call must appear OUTSIDE it, on a line that is not a comment, with
# `install_intake_poll_schedule` as its FIRST token.
# PD-919: F12 moved the canonical definition OUT of install.sh into
# lib-presentation-schedules.sh, which install.sh sources near its top. Parsing
# install.sh alone therefore found only the fail-closed stub
# (`command -v ... || install_intake_poll_schedule() { return 1; }`, which does
# not match the anchored header) and reported GATE 8 red on every tree. The
# definition is now looked for in install.sh first, then — ONLY when install.sh
# actually SOURCES that lib, so a def in an unsourced file is still a dead
# letter — in the lib itself. The CALL is still required in install.sh, outside
# the definition; a defined-but-never-called installer still fails.
# PD-922: "sources" used to be the SUBSTRING test `_LIB_NAME in inst_text`, so a
# COMMENT that merely mentioned the lib counted as sourced and a def inside a
# file install.sh never loads turned GATE 8 green — exactly the dead letter the
# comment above claims to refuse. Only a real `source <path>` / `. <path>` at a
# command position, on a line that is not a comment, whose argument basename is
# the lib name, counts as sourced.
_inst_lines = inst_text.splitlines()
_LIB_NAME = "lib-presentation-schedules.sh"
_SOURCE_RE = re.compile(
    r"(?:^|[;&|]|\bthen\b|\bdo\b|\belse\b|\{|\()\s*(?:source|\.)\s+"
    r"(\"[^\"]*\"|'[^']*'|[^\s;]+)"
)

def _sources_lib(lines, lib_name):
    for _line in lines:
        _s = _line.strip()
        if not _s or _s.startswith("#"):
            continue
        for _m in _SOURCE_RE.finditer(_line):
            _arg = _m.group(1).strip("\"'").rsplit("/", 1)[-1].strip("\"'")
            if _arg == lib_name:
                return True
    return False

def _installer_def(lines):
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*install_intake_poll_schedule\(\)\s*\{\s*$", line):
            start = i
            break
    end = None
    if start is not None:
        for j in range(start + 1, len(lines)):
            if lines[j].startswith("}"):
                end = j
                break
    return start, end

_d_start, _d_end = _installer_def(_inst_lines)
_def_in_install = True
if _d_start is None or _d_end is None:
    _lib = inst.parent / _LIB_NAME
    _lib_lines = []
    if _lib.is_file() and _sources_lib(_inst_lines, _LIB_NAME):
        _lib_lines = _lib.read_text(encoding="utf-8", errors="replace").splitlines()
    _d_start, _d_end = _installer_def(_lib_lines)
    _def_in_install = False
if _d_start is None or _d_end is None:
    fails.append("(4) neither install.sh nor the " + _LIB_NAME + " it sources defines an install_intake_poll_schedule() body ending at a column-0 `}` -- the door cannot prove the installer is callable, so the poll is never scheduled")
else:
    _calls = [
        _line for _i, _line in enumerate(_inst_lines)
        if not (_def_in_install and _d_start <= _i <= _d_end)
        and not _line.lstrip().startswith("#")
        and _line.split()
        and _line.split()[0] == "install_intake_poll_schedule"
    ]
    if not _calls:
        fails.append("(4) install.sh never CALLS install_intake_poll_schedule outside its own definition -- the poll is never scheduled (staged submissions sit forever)")
if "_FIX61_RC=0" not in inst_text or "_FIX61_RC=$?" not in inst_text:
    fails.append("(5) install.sh does not latch the FIX 61 installer rc (_FIX61_RC) -- a failed schedule install would be swallowed")
if fails:
    print("GATE8_FAIL: FIX 61 intake-poll schedule wiring violated:")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("GATE8_PASS: intake-poll scheduled path wired -- template + poll script exist, "
      "install.sh (or the " + _LIB_NAME + " it sources) defines and install.sh CALLS "
      "install_intake_poll_schedule, rc is latched (FIX 61).")
PYEOF
if [ "$GATE8_RC" -ne 0 ]; then
  echo "GATE 8 FAILED: FIX 61 intake-poll schedule wiring violated -- see GATE8_FAIL above." >&2
  FAILED=1
fi

# ---------------------------------------------------------------------------
if [ ! -f "$DEPT_STAMP" ]; then
    fail "provenance stamp $DEPT_STAMP is MISSING — the installed manifest carries no recorded provenance; run the reinstall to restamp (restamp_manifest_source, FIX 113)"
else
    # PD-009: parse the stamp with python, not a grep pipeline. The old
    # `grep -o 'content_sha256=[0-9a-fA-F]*' | head | cut` matched a SUBSTRING
    # anywhere on a line (a comment, a longer key, a quoted example) and silently
    # took the first hit. This reads key=value lines and takes the value only when
    # the key is EXACTLY content_sha256; nothing else prints anything.
    STAMP_SHA="$(python3 - "$DEPT_STAMP" <<'PYSTAMP'
import sys
with open(sys.argv[1], encoding="utf-8", errors="replace") as _fh:
    _lines = _fh.read().splitlines()
for line in _lines:
    key, sep, value = line.partition("=")
    if sep and key.strip() == "content_sha256":
        print(value.strip())
        break
PYSTAMP
)"
    DEPT_MANIFEST_SHA="$(sha "$DEPT_MANIFEST")"
    if [ -z "$STAMP_SHA" ]; then
        fail "provenance stamp $DEPT_STAMP carries no parseable content_sha256= line — run the reinstall to restamp (FIX 113)"
    elif [ "$STAMP_SHA" != "$DEPT_MANIFEST_SHA" ]; then
        fail "provenance stamp $DEPT_STAMP records content_sha256=${STAMP_SHA:0:16}… but the department manifest's actual sha256 is ${DEPT_MANIFEST_SHA:0:16}… — the stamp is STALE (indistinguishable from tampering); run the reinstall to restamp (FIX 113)"
    else
        echo "  OK: provenance stamp matches the department manifest (${STAMP_SHA:0:16}…)"
    fi
fi

python3 - "$REPO_MANIFEST" "$DEPT_MANIFEST" <<'PYMANIFEST' || DRIFT=1
import hashlib
import json
import sys
from pathlib import Path

def csha(p):
    obj = json.loads(Path(p).read_text(encoding="utf-8"))
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest(), (obj.get("manifest_version") if isinstance(obj, dict) else None)

repo_path, dept_path = sys.argv[1], sys.argv[2]
try:
    rsha, rver = csha(repo_path)
except Exception as exc:
    print(f"  DRIFT: repo manifest {repo_path} unreadable/unparseable ({exc})", file=sys.stderr)
    sys.exit(1)
try:
    dsha, dver = csha(dept_path)
except Exception as exc:
    print(f"  DRIFT: department manifest {dept_path} unreadable/unparseable ({exc})", file=sys.stderr)
    sys.exit(1)
if rsha != dsha:
    print(f"  DRIFT: manifest copies differ — repo PIPELINE-MANIFEST.json "
          f"(manifest_version={rver!r}, content {rsha[:16]}…) vs department copy "
          f"(manifest_version={dver!r}, content {dsha[:16]}…). The version field cannot "
          f"detect same-version content edits; content hash is the comparator. Run the "
          f"reinstall/update roll to re-materialize the department manifest and restamp.",
          file=sys.stderr)
    sys.exit(1)
print(f"  OK: department manifest content matches the repo copy (manifest_version={rver})")
sys.exit(0)
PYMANIFEST

if [ "$DRIFT" -ne 0 ] || [ "${FAILED:-0}" -ne 0 ]; then
    echo "[$PROG] FAILED: drift or gate failure detected (DRIFT=$DRIFT FAILED=${FAILED:-0}; see DRIFT/GATE8_FAIL lines above). The sanctioned repair is the reinstall/update roll — refresh-dept-scripts.py re-mirrors the department from the repo and restamps MANIFEST-SOURCE.txt (FIX 113)." >&2
    exit 11
fi
echo "  GATE-D PASSED: department copy == repo copy; provenance stamp current."
exit 0
