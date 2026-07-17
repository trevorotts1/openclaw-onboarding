#!/usr/bin/env python3
"""exemplar_injection.py — A-U9 (master unit U9): exemplar convention +
write-time injection, CALIBRATION-ONLY clause + injection receipts.

WHY THIS EXISTS
----------------
Master spec v2 A.9's honest cross-skill inventory found the fleet-wide
``exemplars/`` convention **NOT-FOUND** — no content skill shipped a gold
output + rationale + provenance a writer could see BEFORE drafting. Skill 58's
style engines already prove the pattern works (``style-engines/vulnerable.md``
etc. carry a "WORKED-EXAMPLE CALIBRATION" passage wrapped in a
"CALIBRATION ONLY … never copy its wording, its topic, or its phrasing"
clause). This module generalizes that pattern into a reusable, fleet-wide,
key-free, deterministic mechanism any content skill can call at write time:

  1. ``discover_packs`` / ``select_exemplars`` — find the 1-2 applicable
     ``exemplars/<deliverable-type>/<slug>/`` packs for a deliverable type
     (+ optional persona-register refinement), skill-by-skill.
  2. ``build_injection_block`` — wrap the selected packs' gold output in the
     Skill-58 CALIBRATION-ONLY clause, verbatim-adapted, ready to append to
     the writer prompt.
  3. ``write_injection_receipt`` — leave a receipt (never a bare claim) at
     ``routing/exemplar-injection.json`` recording exactly which exemplar ids
     + content hashes were (or were not) injected, so the judge can prove it
     happened from primary-source evidence.

EXEMPLAR PACK CONVENTION
-------------------------
``<skill-dir>/exemplars/<deliverable-type>/<slug>/`` = exactly three files:

  - ``gold-output.md``   — the gold output itself (anonymized / fictional-
                            brand only — the repo is fleet-wide: no client
                            names, standing rule).
  - ``WHY-GOOD.md``      — which register, which close, which structure
                            earns the grade (never just the surface text).
  - ``provenance.json``  — source, date, Quality-Control score if harvested,
                            and an ``llm_content_review`` receipt (an LLM
                            read — never a bare pattern-match/name-grep —
                            confirming zero client-identifying content).

A directory missing any of the three files is an INCOMPLETE pack and is
never surfaced by ``discover_packs`` — a partial pack is not a pack.

DEGRADE POSTURE (acceptance (d))
---------------------------------
``select_exemplars`` returns ``[]`` (never an error, never a fabricated
match) whenever no applicable pack exists for the deliverable type.
``build_injection_block`` returns ``None`` on an empty pack list — callers
MUST treat ``None`` as "inject nothing," reproducing today's (pre-A-U9)
behavior exactly. There is no such thing as an empty injection block.

stdlib-only, deterministic, no network, no key — runs identically on every
box (mirrors ``persona_crosswalk.py`` / ``fab_qc.py``'s posture).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))

REQUIRED_PACK_FILES = ("gold-output.md", "WHY-GOOD.md", "provenance.json")

# Skill-58 style-engines' own "WORKED-EXAMPLE CALIBRATION" passage
# (style-engines/vulnerable.md / passionate.md / provocative.md /
# counter-intuitive.md), verbatim-adapted from a single-voice-engine frame to
# a generic content-skill frame per the A-U9 build text ("wrapped in the
# Skill-58 clause verbatim-adapted"). The three load-bearing sentences —
# "CALIBRATION ONLY", "It exists so the writer can see/hear … before
# drafting", "Never copy its wording, its topic, or its phrasing" — are kept
# intact; only the frame noun changes (episode/beat -> deliverable).
CALIBRATION_HEADER = "## EXEMPLAR CALIBRATION"
CALIBRATION_ONLY_CLAUSE = (
    "CALIBRATION ONLY. The passage(s) below are a target-quality sample for "
    "this deliverable type, on an illustrative topic. They exist so the "
    "writer can see the register, structure, and close before drafting. "
    "Never copy their wording, their topic, or their phrasing into the real "
    "deliverable. Every real deliverable is built fresh from this client's "
    "own material."
)


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def discover_packs(skill_dir: str, deliverable_type: Optional[str] = None) -> list:
    """Scan ``<skill_dir>/exemplars/<deliverable_type>/<slug>/`` for COMPLETE
    packs (all three ``REQUIRED_PACK_FILES`` present). Incomplete directories
    are silently skipped — never raises, never partially-injects. When
    ``deliverable_type`` is ``None``, scans every deliverable-type directory
    under ``exemplars/``. Returns a deterministically-ordered list (sorted by
    deliverable_type, then slug) of pack dicts:

        {exemplar_id, skill, deliverable_type, slug, pack_dir,
         gold_output_path, gold_output_hash, why_good_path, why_good_hash,
         provenance_path, provenance}

    ``gold_output_hash`` / ``why_good_hash`` are ``sha256:<hex>`` of the
    file's bytes — the primary-source proof ``write_injection_receipt``
    carries forward into the evidence tree."""
    root = os.path.join(skill_dir, "exemplars")
    if not os.path.isdir(root):
        return []

    if deliverable_type:
        type_dirs = [deliverable_type]
    else:
        try:
            type_dirs = sorted(
                d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))
            )
        except OSError:
            return []

    skill_slug = os.path.basename(os.path.normpath(skill_dir))
    out = []
    for dt in type_dirs:
        dt_dir = os.path.join(root, dt)
        if not os.path.isdir(dt_dir):
            continue
        try:
            slugs = sorted(
                s for s in os.listdir(dt_dir) if os.path.isdir(os.path.join(dt_dir, s))
            )
        except OSError:
            continue
        for slug in slugs:
            pack_dir = os.path.join(dt_dir, slug)
            files = {name: os.path.join(pack_dir, name) for name in REQUIRED_PACK_FILES}
            if not all(os.path.isfile(p) for p in files.values()):
                continue  # incomplete pack — never a pack, never injected

            try:
                with open(files["provenance.json"], encoding="utf-8") as f:
                    provenance = json.load(f)
                if not isinstance(provenance, dict):
                    provenance = {}
            except (OSError, json.JSONDecodeError):
                provenance = {}

            fallback_id = f"{skill_slug}/{dt}/{slug}"
            exemplar_id = provenance.get("exemplar_id") or fallback_id

            out.append({
                "exemplar_id": exemplar_id,
                "skill": skill_slug,
                "deliverable_type": dt,
                "slug": slug,
                "pack_dir": pack_dir,
                "gold_output_path": files["gold-output.md"],
                "gold_output_hash": _sha256_file(files["gold-output.md"]),
                "why_good_path": files["WHY-GOOD.md"],
                "why_good_hash": _sha256_file(files["WHY-GOOD.md"]),
                "provenance_path": files["provenance.json"],
                "provenance": provenance,
            })
    return out


# --------------------------------------------------------------------------- #
# Selection — deliverable_type + optional persona_register refinement
# --------------------------------------------------------------------------- #
def select_exemplars(skill_dir: str, deliverable_type: str, *,
                     persona_register: str = "", limit: int = 2) -> list:
    """Return up to ``limit`` applicable exemplar packs (the A-U9 build text:
    "1-2 exemplars for the deliverable type + persona register"). Empty
    ``deliverable_type`` or no matching pack both return ``[]`` — the caller
    MUST degrade to no-injection, never fabricate a pack. When
    ``persona_register`` is given and at least one discovered pack's
    ``provenance.json`` carries a matching ``persona_register`` tag, ONLY
    register-matching packs are returned; otherwise every pack for the
    deliverable type is eligible (register-agnostic packs calibrate register
    generically). Deterministic order (sorted by slug) — repeated calls with
    the same inputs return the same packs in the same order."""
    if not deliverable_type or not isinstance(deliverable_type, str):
        return []
    packs = discover_packs(skill_dir, deliverable_type=deliverable_type)
    if not packs:
        return []

    if persona_register:
        wanted = persona_register.strip().lower()
        register_matches = [
            p for p in packs
            if str((p.get("provenance") or {}).get("persona_register") or "")
               .strip().lower() == wanted
        ]
        pool = register_matches or packs
    else:
        pool = packs

    pool = sorted(pool, key=lambda p: p["slug"])
    limit = max(0, int(limit))
    return pool[:limit]


# --------------------------------------------------------------------------- #
# Write-time injection block — the CALIBRATION-ONLY wrapped prompt fragment
# --------------------------------------------------------------------------- #
def build_injection_block(packs: list) -> Optional[str]:
    """Wrap the selected packs' gold output + WHY-GOOD rationale in the
    CALIBRATION-ONLY clause, ready to append to the writer prompt. Returns
    ``None`` when ``packs`` is empty — acceptance (d): "prompts without an
    applicable pack degrade to today's behavior (no empty-injection
    block)". Never raises on an unreadable pack file — that pack is skipped
    (degrade, never fabricate); if every pack turns out unreadable the
    result is still ``None``, never an empty-but-present block."""
    if not packs:
        return None

    sections = []
    for p in packs:
        try:
            with open(p["gold_output_path"], encoding="utf-8") as f:
                gold = f.read().strip()
            with open(p["why_good_path"], encoding="utf-8") as f:
                why = f.read().strip()
        except OSError:
            continue
        if not gold:
            continue
        sections.append(
            f"### Exemplar: {p['exemplar_id']}\n\n{gold}\n\n"
            f"_Why this earns the grade:_\n\n{why}"
        )

    if not sections:
        return None

    lines = [CALIBRATION_HEADER, "", CALIBRATION_ONLY_CLAUSE, "", *sections]
    return "\n\n".join(lines).strip() + "\n"


# --------------------------------------------------------------------------- #
# Injection receipt — routing/exemplar-injection.json (receipts, never claims)
# --------------------------------------------------------------------------- #
def write_injection_receipt(evidence_root: str, packs: list, *, deliverable_type: str,
                            persona_register: str = "", page: Optional[str] = None) -> dict:
    """Append one injection record to ``routing/exemplar-injection.json``
    (created on first call, accumulated across multiple pages/calls in the
    same evidence tree — the per-page-bundle-receipts pattern). Each record
    carries the exemplar id + content hash of every pack actually selected,
    so a judge can independently re-hash the shipped exemplar files and
    confirm the receipt did not fabricate a match. ``injected: false`` with
    an empty ``exemplars`` list is written (never a raise, never a skipped
    write) when ``packs`` is empty, so a "no applicable pack" outcome is
    itself an honest, auditable receipt — matching the repo's
    ``embedding: deferred`` receipt posture elsewhere."""
    routing = os.path.join(evidence_root, "routing")
    os.makedirs(routing, exist_ok=True)
    path = os.path.join(routing, "exemplar-injection.json")

    doc = None
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get("injections"), list):
                doc = loaded
        except (OSError, json.JSONDecodeError):
            doc = None
    if doc is None:
        doc = {"injections": []}

    doc["injections"].append({
        "page": page,
        "deliverable_type": deliverable_type,
        "persona_register": persona_register or None,
        "injected": bool(packs),
        "exemplars": [
            {
                "exemplar_id": p["exemplar_id"],
                "skill": p["skill"],
                "deliverable_type": p["deliverable_type"],
                "slug": p["slug"],
                "content_hash": p["gold_output_hash"],
            }
            for p in packs
        ],
        "generated_at": _ts(),
    })
    doc["generated_at"] = _ts()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    return doc


if __name__ == "__main__":
    # Offline self-test — real shipped packs (this repo's own exemplars/),
    # no network, no key.
    import tempfile

    ok = True

    def check(label, cond):
        global ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    _repo = os.path.dirname(_HERE)
    skill6_dir = os.path.join(_repo, "06-ghl-install-pages")
    skill35_dir = os.path.join(_repo, "35-social-media-planner")

    for category in ("lead", "buyer", "event"):
        packs = discover_packs(skill6_dir, deliverable_type=category)
        check(f"skill 6 ships >=1 complete {category!r} pack", len(packs) >= 1)
        if packs:
            for f in REQUIRED_PACK_FILES:
                check(f"{category} pack file present: {f}",
                      os.path.isfile(os.path.join(packs[0]["pack_dir"], f)))

    s35_packs = discover_packs(skill35_dir)
    check("skill 35 ships >=1 complete pack", len(s35_packs) >= 1)

    selected = select_exemplars(skill6_dir, "lead")
    check("select_exemplars finds the shipped lead pack", len(selected) >= 1)
    check("select_exemplars never exceeds the default limit of 2", len(selected) <= 2)

    none_selected = select_exemplars(skill6_dir, "no-such-deliverable-type")
    check("select_exemplars degrades to [] for an unknown deliverable_type",
          none_selected == [])
    check("select_exemplars degrades to [] for an empty deliverable_type",
          select_exemplars(skill6_dir, "") == [])

    block = build_injection_block(selected)
    check("build_injection_block wraps the CALIBRATION-ONLY clause", (
        block is not None and CALIBRATION_HEADER in block
        and "CALIBRATION ONLY" in block
        and "Never copy their wording" in block
    ))
    empty_block = build_injection_block([])
    check("build_injection_block returns None for an empty pack list (d)",
          empty_block is None)

    with tempfile.TemporaryDirectory() as td:
        receipt = write_injection_receipt(
            td, selected, deliverable_type="lead", page="Optin")
        on_disk_path = os.path.join(td, "routing", "exemplar-injection.json")
        check("write_injection_receipt writes routing/exemplar-injection.json",
              os.path.isfile(on_disk_path))
        with open(on_disk_path, encoding="utf-8") as f:
            on_disk = json.load(f)
        check("on-disk receipt round-trips", on_disk == receipt)
        hashes_on_disk = {e["content_hash"] for i in on_disk["injections"] for e in i["exemplars"]}
        real_hashes = {p["gold_output_hash"] for p in selected}
        check("receipt hashes match the shipped exemplars' real sha256",
              hashes_on_disk == real_hashes and bool(hashes_on_disk))

        # A second call accumulates, never clobbers.
        write_injection_receipt(td, [], deliverable_type="unmatched", page="ThankYou")
        with open(on_disk_path, encoding="utf-8") as f:
            after_second = json.load(f)
        check("receipt accumulates across calls (2 injections recorded)",
              len(after_second["injections"]) == 2)
        check("a no-match call is still an honest receipt (injected=false, exemplars=[])",
              after_second["injections"][1]["injected"] is False
              and after_second["injections"][1]["exemplars"] == [])

    for p in selected:
        review = (p.get("provenance") or {}).get("llm_content_review") or {}
        check(f"{p['exemplar_id']} carries an llm_content_review receipt (never a name-grep)",
              review.get("reviewed") is True and bool(review.get("verdict")))

    print("== exemplar_injection self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    raise SystemExit(0 if ok else 1)
