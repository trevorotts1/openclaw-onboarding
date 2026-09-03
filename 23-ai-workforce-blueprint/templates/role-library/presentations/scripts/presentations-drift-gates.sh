#!/usr/bin/env bash
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
if [ ! -f "$DEPT_STAMP" ]; then
    fail "provenance stamp $DEPT_STAMP is MISSING — the installed manifest carries no recorded provenance; run the reinstall to restamp (restamp_manifest_source, FIX 113)"
else
    STAMP_SHA="$(grep -o 'content_sha256=[0-9a-fA-F]*' "$DEPT_STAMP" | head -1 | cut -d= -f2)"
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

if [ "$DRIFT" -ne 0 ]; then
    echo "[$PROG] FAILED: repo/department/provenance drift (see DRIFT lines above). The sanctioned repair is the reinstall/update roll — refresh-dept-scripts.py re-mirrors the department from the repo and restamps MANIFEST-SOURCE.txt (FIX 113)." >&2
    exit 11
fi
echo "  GATE-D PASSED: department copy == repo copy; provenance stamp current."
exit 0
