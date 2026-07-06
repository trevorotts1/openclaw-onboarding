#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: ROLE-SOP REGISTRY STAMPER + CHECKER
# -----------------------------------------------------------------------------
# Registers the 7 dispatchable role SOPs under 53-book-writer/roles/ into
# roles/_index.json with a CANONICAL content_sha per role SOP (and the optional
# PERSONAS.json palette), names the SOLE dispatcher (the assembler foreman
# run_book_writer.py), and enforces the registry is complete + not stale.
#
# This is the Skill-53-local analogue of 23-ai-workforce-blueprint's
# hash-content-manifest.py: editing ANY role SOP requires re-running this stamper
# (the content_sha re-stamp) or the --check gate (wired into qc-book-writer.sh +
# verify.sh) fails. The content_sha is computed over the CANONICAL text with a
# stable normalization (CRLF->LF, strip one trailing newline) so editor/EOL noise
# is not a content change and two identical SOPs hash identically.
#
#   AF-BK-ROLE-REGISTRY — a registered role SOP is missing, unregistered, or its
#                         stored content_sha is stale vs the file on disk.
#
# EXIT: 0 PASS · 1 STALE/INCOMPLETE (--check) · 2 USAGE/IO.
# USAGE:
#   python3 hash_role_index.py            # stamp roles/_index.json in place
#   python3 hash_role_index.py --dry-run  # compute, do not write
#   python3 hash_role_index.py --check    # assert complete + not stale (gate mode)
# =============================================================================
"""Deterministic role-SOP registry stamper/checker for the Skill 53 Book Writer."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_ROLES_DIR = _SKILL_DIR / "roles"
_INDEX_PATH = _ROLES_DIR / "_index.json"

MANIFEST_SCHEMA = "1.0"
DEFAULT_CONTENT_VERSION = "1.0.0"

# The SOLE dispatcher (foreman): roles never invoke each other — the deterministic
# assembler pipeline is the ONLY dispatcher (see every role SOP's "Never dispatch a
# sibling role" clause).
DISPATCHER = {
    "kind": "foreman",
    "entry": "book-writer-entry.sh",
    "orchestrator": "run_book_writer.py",
    "note": "The main agent acts as foreman via run_book_writer.py (dispatched through "
            "book-writer-entry.sh). Roles are dispatched by the foreman only and never "
            "invoke each other.",
}

# The 7 dispatchable role SOPs (slug -> filename), in pipeline order.
ROLE_SOPS = [
    ("avatar-analyst", "AVATAR-ANALYST.md", "P1-AVATAR"),
    ("tone-analyst", "TONE-ANALYST.md", "P2-TONE"),
    ("title-strategist", "TITLE-STRATEGIST.md", "P3-TITLES-GATE"),
    ("book-architect", "BOOK-ARCHITECT.md", "P4-OUTLINE-GATE"),
    ("chapter-writer", "CHAPTER-WRITER.md", "P5-CHAPTERS"),
    ("packager", "PACKAGER.md", "P6-PACKAGE"),
    ("reviser", "REVISER.md", "P6-PACKAGE"),
]

# The OPTIONAL fictional-voice palette (DATA only, never a role) the TONE-ANALYST
# may draw on for an N/A tone influence. Registered so an edit to it is also caught.
PERSONA_PALETTE = ("book-writer-personas", "PERSONAS.json")


def normalize_canonical(text: str) -> bytes:
    """CRLF->LF, strip a single trailing newline; then UTF-8 bytes for sha256."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    return text.encode("utf-8")


def content_sha_of_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(
        normalize_canonical(path.read_text(encoding="utf-8"))).hexdigest()


def _bump_patch(version: str) -> str:
    try:
        major, minor, patch = (int(p) for p in str(version).split("."))
        return "%d.%d.%d" % (major, minor, patch + 1)
    except (ValueError, TypeError):
        return DEFAULT_CONTENT_VERSION


def _resolve_version(prior_ver, prior_sha, new_sha) -> str:
    if not prior_ver:
        return DEFAULT_CONTENT_VERSION
    if prior_sha == new_sha:
        return prior_ver
    return _bump_patch(prior_ver)


def _load_index() -> dict:
    if _INDEX_PATH.is_file():
        try:
            return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def stamp(data: dict) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    prior_roles = {r.get("path"): r for r in data.get("roles", []) if isinstance(r, dict)}
    roles_out = []
    for slug, fname, phase in ROLE_SOPS:
        rel = "roles/%s" % fname
        abspath = _ROLES_DIR / fname
        prev = prior_roles.get(rel, {})
        if not abspath.is_file():
            roles_out.append({"slug": slug, "path": rel, "phase": phase,
                              "dispatched_by": "foreman",
                              "content_sha": "sha256:MISSING",
                              "content_version": prev.get("content_version", DEFAULT_CONTENT_VERSION),
                              "content_hashed_at": now_iso})
            continue
        new_sha = content_sha_of_file(abspath)
        new_ver = _resolve_version(prev.get("content_version"), prev.get("content_sha"), new_sha)
        roles_out.append({"slug": slug, "path": rel, "phase": phase,
                          "dispatched_by": "foreman",
                          "content_sha": new_sha, "content_version": new_ver,
                          "content_hashed_at": now_iso})

    # optional persona palette
    palette_out = []
    pslug, pfname = PERSONA_PALETTE
    pabs = _SKILL_DIR / pfname
    if pabs.is_file():
        prev = next((p for p in data.get("persona_palette", [])
                     if isinstance(p, dict) and p.get("path") == pfname), {})
        psha = content_sha_of_file(pabs)
        palette_out.append({"slug": pslug, "path": pfname, "kind": "data-only-palette",
                            "content_sha": psha,
                            "content_version": _resolve_version(
                                prev.get("content_version"), prev.get("content_sha"), psha),
                            "content_hashed_at": now_iso})

    return {
        "$schema": "https://openclaw.ai/schemas/book-writer-role-index/v1",
        "contract": "book-writer-role-index",
        "skill": "book-writer",
        "skill_number": 53,
        "description": "Registry of the 7 dispatchable role SOPs under 53-book-writer/roles/, "
                       "each with a canonical content_sha (re-stamp with hash_role_index.py after "
                       "any role SOP edit). The SOLE dispatcher is the foreman (run_book_writer.py, "
                       "via book-writer-entry.sh); roles never invoke each other. PERSONAS.json is a "
                       "DATA-only fictional-voice palette, not a role.",
        "dispatcher": DISPATCHER,
        "roles": roles_out,
        "persona_palette": palette_out,
        "content_manifest": {
            "algo": "sha256",
            "normalize": ["lf-newlines", "strip-trailing-nl"],
            "generator": "scripts/hash_role_index.py",
            "generated_at": now_iso,
            "manifest_schema": MANIFEST_SCHEMA,
        },
    }


def check(data: dict):
    problems = []
    cm = data.get("content_manifest")
    if not isinstance(cm, dict) or cm.get("algo") != "sha256":
        problems.append("content_manifest header missing/invalid (run hash_role_index.py)")
    if cm and cm.get("manifest_schema") != MANIFEST_SCHEMA:
        problems.append("content_manifest.manifest_schema %r != %r"
                        % (cm.get("manifest_schema"), MANIFEST_SCHEMA))
    disp = data.get("dispatcher")
    if not isinstance(disp, dict) or not disp.get("orchestrator"):
        problems.append("dispatcher not named (expected the foreman run_book_writer.py)")

    registered = {r.get("path"): r for r in data.get("roles", []) if isinstance(r, dict)}
    for slug, fname, _phase in ROLE_SOPS:
        rel = "roles/%s" % fname
        abspath = _ROLES_DIR / fname
        rec = registered.get(rel)
        if rec is None:
            problems.append("role %s (%s) present on disk but ABSENT from _index.json" % (slug, rel))
            continue
        if not rec.get("content_sha") or rec["content_sha"].endswith("MISSING"):
            problems.append("role %s: missing content_sha" % slug)
            continue
        if not rec.get("content_version"):
            problems.append("role %s: missing content_version" % slug)
        if not abspath.is_file():
            problems.append("role %s: file not found (%s)" % (slug, rel))
            continue
        fresh = content_sha_of_file(abspath)
        if fresh != rec["content_sha"]:
            problems.append("role %s: STALE content_sha — re-run hash_role_index.py" % slug)
    # coverage: any roles/*.md role SOP on disk that is NOT registered
    for md in sorted(_ROLES_DIR.glob("*.md")):
        rel = "roles/%s" % md.name
        if rel not in registered:
            problems.append("role SOP %s on disk but not registered in _index.json" % rel)
    # palette (optional but if present must not be stale)
    pslug, pfname = PERSONA_PALETTE
    pabs = _SKILL_DIR / pfname
    if pabs.is_file():
        prec = next((p for p in data.get("persona_palette", [])
                     if isinstance(p, dict) and p.get("path") == pfname), None)
        if prec is None:
            problems.append("persona palette %s present but not registered" % pfname)
        elif content_sha_of_file(pabs) != prec.get("content_sha"):
            problems.append("persona palette %s: STALE content_sha — re-run hash_role_index.py" % pfname)
    return (len(problems) == 0), problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer role-SOP registry stamper/checker (Skill 53).")
    ap.add_argument("--dry-run", action="store_true", help="compute but do not write")
    ap.add_argument("--check", action="store_true", help="assert complete + not stale; exit 1 on drift")
    args = ap.parse_args(argv)

    if args.check:
        data = _load_index()
        if not data:
            print("AF-BK-ROLE-REGISTRY: roles/_index.json missing/empty — run hash_role_index.py",
                  file=sys.stderr)
            return 1
        ok, problems = check(data)
        if ok:
            print("✓ role registry CHECK PASS — %d role SOPs registered, dispatcher named, "
                  "no stale content_sha." % len(ROLE_SOPS))
            return 0
        print("✗ role registry CHECK FAIL — %d problem(s):" % len(problems), file=sys.stderr)
        for p in problems:
            print("    - %s" % p, file=sys.stderr)
        return 1

    stamped = stamp(_load_index())
    if args.dry_run:
        print(json.dumps(stamped, indent=2))
        print("\n[DRY RUN] roles/_index.json NOT written.")
        return 0
    _ROLES_DIR.mkdir(parents=True, exist_ok=True)
    _INDEX_PATH.write_text(json.dumps(stamped, indent=2) + "\n", encoding="utf-8")
    print("stamped roles/_index.json — %d role SOPs + %d palette file(s), dispatcher=%s"
          % (len(stamped["roles"]), len(stamped["persona_palette"]),
             stamped["dispatcher"]["orchestrator"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
