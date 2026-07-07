#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: AVATAR-HANDOFF GATE  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# The pre-P1 phase P0A-AVATAR DELEGATES to Skill 52 avatar-alchemist prompts
# 01..03 BY PATH — no Skill 52 file is ever copied into this skill. This gate is
# the fail-closed enforcement of that delegation (SPEC 3.2 item 1; the exact
# handoff pattern Skill 53 models, but reference-only). It decides three AF codes:
#
#   AF-AW-AVATAR-MISSING        — working/avatar.md is absent, empty, or
#                                 whitespace-only: the Skill 52 handoff produced
#                                 no avatar dossier for the downstream authoring
#                                 stages to consume.
#   AF-AW-AVATAR-HANDOFF-DRIFT  — a referenced Skill 52 avatar prompt
#                                 (aa-01/aa-02/aa-03 x system|user|methodology) is
#                                 missing at its pinned 52-avatar-alchemist path OR
#                                 its sha256 != the manifest avatar_handoff pin
#                                 (Skill 52 not installed, tampered, or
#                                 version-drifted). The reference-by-path handoff
#                                 must resolve to the EXACT pinned IP or fail closed
#                                 — never a silent stale-IP fallback.
#   AF-AW-AVATAR-COPIED         — a Skill 52 avatar prompt (01/02/03-*) was COPIED
#                                 into this skill's own tree instead of referenced
#                                 by path (no-copy law; the avatar IP stays
#                                 single-sourced in Skill 52).
#
# The pins live in ONE place: ANTHOLOGY-MANIFEST.json -> avatar_handoff.stages
# (stage_id -> files{name: sha256}). Model-free, provider-neutral, stdlib only:
# no LLM, no network — the same decision on every box.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_aw_avatar.py <avatar.md> [--manifest FILE] [--skill52-dir DIR]
#                           [--scan-root DIR] [--json]
#        prove_aw_avatar.py --self-test
# =============================================================================
"""Fail-closed avatar-handoff (Skill 52 delegation) gate for the Anthology Writer."""

import argparse
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _aw_common as c  # noqa: E402

AF_AVATAR_MISSING = "AF-AW-AVATAR-MISSING"
AF_AVATAR_DRIFT = "AF-AW-AVATAR-HANDOFF-DRIFT"
AF_AVATAR_COPIED = "AF-AW-AVATAR-COPIED"

_SKILL_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_MANIFEST = _SKILL_DIR / "ANTHOLOGY-MANIFEST.json"
# Skill 52 is a SIBLING skill; its avatar prompts are read in place (never copied).
_DEFAULT_SKILL52 = _SKILL_DIR.parent / "52-avatar-alchemist" / "prompts"
# The no-copy scan walks THIS skill's own tree by default.
_DEFAULT_SCAN_ROOT = _SKILL_DIR
_FIX = _SKILL_DIR / "test-fixtures"

# The three avatar-front stage directory names and the three prompt files that
# make up each — the telltale shape of a COPIED Skill 52 avatar prompt.
_AVATAR_STAGE_DIRS = {"01-avatar-questions-1-30", "02-avatar-questions-31-32",
                      "03-rewrite-avatar"}
_PROMPT_FILES = {"system.md", "user.md", "methodology.md"}

# Deliberately-planted attack fixtures live under these path segments; the DEFAULT
# no-copy scan of the shipped skill tree excludes them (they exist precisely to
# prove the gate REJECTS a copy / a drift). An explicit --scan-root pointed AT a
# fixture computes rel paths relative to that root, so the planted copy is seen.
_SKIP_SEGMENTS = ("/test-fixtures/attack/", "/broken-variants/", "/drifted-prompts/")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _load_stages(manifest_path: Path):
    """Return avatar_handoff.stages from ANTHOLOGY-MANIFEST.json (the ONE pin
    source). Each stage carries stage_id + files{name: sha256}."""
    obj = c.read_json(manifest_path)
    handoff = obj.get("avatar_handoff", {}) if isinstance(obj, dict) else {}
    return handoff.get("stages") or []


def _scan_for_copies(scan_root: Path, pinned_hashes):
    """Return [(rel, why)] for every file under scan_root that is a COPIED Skill 52
    avatar prompt: (1) a prompt file inside a telltale avatar stage directory, or
    (2) a byte-identical copy of a pinned Skill 52 avatar prompt (sha256 match).
    Deliberately-planted attack fixtures (test-fixtures/attack, broken-variants,
    drifted-prompts) are excluded so the shipped tree scans clean."""
    out = []
    if not scan_root.is_dir():
        return out
    for root, dirs, files in os.walk(scan_root):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for fn in files:
            p = Path(root) / fn
            rel = "/" + os.path.relpath(str(p), str(scan_root)).replace(os.sep, "/")
            if any(seg in rel for seg in _SKIP_SEGMENTS):
                continue
            parent = Path(root).name
            if parent in _AVATAR_STAGE_DIRS and fn in _PROMPT_FILES:
                out.append((rel.lstrip("/"),
                            "a Skill 52 avatar prompt directory (%s/%s) was copied into "
                            "the skill tree" % (parent, fn)))
                continue
            if pinned_hashes and fn.lower().endswith(".md"):
                try:
                    if _sha256(p) in pinned_hashes:
                        out.append((rel.lstrip("/"),
                                    "byte-identical copy of a pinned Skill 52 avatar prompt"))
                except OSError:
                    pass
    return out


def evaluate(avatar_path, manifest_path: Path, skill52_dir: Path, scan_root: Path) -> c.Result:
    r = c.Result("prove_aw_avatar")
    stages = _load_stages(manifest_path)
    if not stages:
        r.fail(AF_AVATAR_DRIFT, "manifest avatar_handoff.stages is empty/absent — no pinned "
               "Skill 52 IP to verify the delegation against")

    # 1) AF-AW-AVATAR-MISSING — the produced dossier must exist and be real prose.
    text = None
    if avatar_path is not None:
        ap = Path(avatar_path)
        if ap.is_file():
            try:
                text = ap.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                text = None
    if text is None or not text.strip():
        r.fail(AF_AVATAR_MISSING, "working/avatar.md is absent, empty, or whitespace-only — the "
               "Skill 52 handoff produced no avatar dossier for the downstream authoring stages")
    else:
        r.note("avatar dossier present (%d stripped words)" % c.word_count(text))

    # 2) AF-AW-AVATAR-HANDOFF-DRIFT — every referenced Skill 52 prompt must resolve
    #    at its pinned path with sha256 == the manifest pin (delegation integrity).
    pinned_hashes = set()
    checked = 0
    for stage in stages:
        sid = str(stage.get("stage_id", ""))
        for fname, want in (stage.get("files") or {}).items():
            pinned_hashes.add(want)
            p = Path(skill52_dir) / sid / fname
            if not p.is_file():
                r.fail(AF_AVATAR_DRIFT, "referenced Skill 52 prompt missing at its pinned path: "
                       "%s/%s (Skill 52 not installed at %s, or the file moved)"
                       % (sid, fname, skill52_dir))
                continue
            got = _sha256(p)
            if got != want:
                r.fail(AF_AVATAR_DRIFT, "%s/%s sha256 drift: got %s… expected %s… (Skill 52 "
                       "tampered or version-drifted from the pinned IP)"
                       % (sid, fname, got[:12], want[:12]))
            else:
                checked += 1
    if checked and not any(code == AF_AVATAR_DRIFT for code, _ in r.violations):
        r.note("all %d referenced Skill 52 avatar prompts resolve at their pinned paths with "
               "matching sha256 (reference-by-path delegation intact)" % checked)

    # 3) AF-AW-AVATAR-COPIED — no Skill 52 avatar prompt may be copied into the tree.
    copies = _scan_for_copies(Path(scan_root), pinned_hashes)
    for rel, why in copies:
        r.fail(AF_AVATAR_COPIED, "%s — %s; the avatar IP stays single-sourced in Skill 52 and is "
               "referenced BY PATH, never copied" % (rel, why))
    if not copies:
        r.note("no Skill 52 avatar prompt copied into the scanned tree (no-copy law)")

    return r


def prove(avatar_path, manifest_path, skill52_dir, scan_root, as_json=False) -> int:
    return evaluate(avatar_path, Path(manifest_path), Path(skill52_dir),
                    Path(scan_root)).emit(as_json)


def self_test() -> int:
    checks = []
    manifest = _DEFAULT_MANIFEST
    s52 = _DEFAULT_SKILL52
    gold = _FIX / "golden" / "avatar.md"

    g = evaluate(gold, manifest, s52, _SKILL_DIR)
    checks.append(("golden avatar handoff PASSes (dossier + Skill 52 delegation intact)", g.passed))

    m = evaluate(_FIX / "attack" / "avatar_empty.md", manifest, s52, _SKILL_DIR)
    checks.append(("empty avatar.md AUTOFAILs", not m.passed))
    checks.append(("...with AF-AW-AVATAR-MISSING",
                   any(code == AF_AVATAR_MISSING for code, _ in m.violations)))

    d = evaluate(gold, manifest, _FIX / "attack" / "drifted-skill52", _SKILL_DIR)
    checks.append(("drifted/absent Skill 52 IP AUTOFAILs", not d.passed))
    checks.append(("...with AF-AW-AVATAR-HANDOFF-DRIFT",
                   any(code == AF_AVATAR_DRIFT for code, _ in d.violations)))

    cp = evaluate(gold, manifest, s52, _FIX / "attack" / "copied-skill52-tree")
    checks.append(("copied Skill 52 avatar prompt AUTOFAILs", not cp.passed))
    checks.append(("...with AF-AW-AVATAR-COPIED",
                   any(code == AF_AVATAR_COPIED for code, _ in cp.violations)))

    return c.selftest_report("prove_aw_avatar", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Anthology Writer avatar-handoff gate (Skill 54).")
    ap.add_argument("path", nargs="?", help="working/avatar.md to prove")
    ap.add_argument("--manifest", default=str(_DEFAULT_MANIFEST),
                    help="manifest carrying avatar_handoff pins")
    ap.add_argument("--skill52-dir", default=str(_DEFAULT_SKILL52),
                    help="Skill 52 prompts dir (default: sibling ../52-avatar-alchemist/prompts)")
    ap.add_argument("--scan-root", default=str(_DEFAULT_SCAN_ROOT),
                    help="tree scanned for copied avatar prompts (default: the skill dir)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("an avatar.md path is required (or use --self-test)")
    return prove(args.path, args.manifest, args.skill52_dir, args.scan_root, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
