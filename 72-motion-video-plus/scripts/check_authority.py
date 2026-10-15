#!/usr/bin/env python3
"""References and authority check for Skill 72 (MG-042).

Mechanically verifies the MG-042 acceptance surface:

1. Dead paths: every skill-relative or repo-relative file path named
   in the entrypoint and authority documents exists on disk.
2. Obsolete promises: no document in the reconciled set carries the
   known-obsolete production claims (the old per-scene character
   rule, the forced 960x540/15fps preview, the three-round / score-8
   critique gate, the two-hour scalability promise, the V1 __setTime
   pipeline presented as the skill itself, mandatory-voice wording,
   a blanket authoring-model vendor ban, fixed render-time
   promises, or the production engines described as untested or
   unimplemented).
3. Required presences: the status-and-delivery pointer in both
   entrypoints, the four mode identifiers in the entrypoints, the
   authority map, and the master contract; the model-agnostic
   interface statement; the MG-034 audio-evidence pointer in the
   critique protocol; PowerPoint playback stated as UNVERIFIED
   wherever a reconciled document discusses PowerPoint playback.
4. Mirror consistency: the repo-integration department-map entry and
   the canonical skill-department-map entry for Skill 72 are the
   same object, and neither carries the obsolete V1 description.

Scope notes: the install fixtures under tests/fixtures/ are
historical snapshots of older installations used by the migration
tests; they are deliberately NOT part of the reconciled set and are
never edited to match current guidance. Historical evidence records
under tests/evidence/ are likewise out of scope: they record what
was true when they were written. Installed and generated trees are
also out of scope: any path under the skill root carrying a
node_modules, dist, or .runtime segment is installed third-party
content or build output, not authored text, and this check governs
authored files only.

Usage:
    python3 scripts/check_authority.py [--root SKILL_DIR]

Exit codes: 0 pass; 1 one or more findings (each printed by name).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ENTRYPOINT_DOCS = [
    "SKILL.md",
    "INSTRUCTIONS.md",
    "MASTERDOC.md",
    "INSTALL.md",
    "QC.md",
    "CORE_UPDATES.md",
    "REPO-INTEGRATION.md",
    "references/authority-map.md",
]

# Documents whose production instructions MG-042 reconciles. Every
# Skill 72 markdown document outside tests/ is in the set; the scan
# below builds it by glob so a new reference is covered automatically.
EXTRA_RECONCILED = [
    "47-movie-producer/SKILL.md",
    "47-movie-producer/INSTRUCTIONS.md",
    "45-design-intelligence-library/SKILL.md",
]

PATH_PREFIXES = (
    "references/",
    "scripts/",
    "assets/",
    "runtime/",
    "tests/",
    "shared-utils/",
    "23-ai-workforce-blueprint/",
    "47-movie-producer/",
    "45-design-intelligence-library/",
    "72-motion-video-plus/",
    "universal-sops/",
)

FOUR_MODES = ["powerpoint_graphic", "vsl_desktop", "vsl_mobile", "standalone_video"]

# (finding name, regex, human reason). Applied to the reconciled set.
OBSOLETE = [
    (
        "OBSOLETE_CHAR_RULE",
        re.compile(r"2,?000 to 4,?000 characters"),
        "the old per-scene 2,000 to 4,000 character rule; chunking is a "
        "per-request transport cap with no minimum (MG-020/MG-023)",
    ),
    (
        "OBSOLETE_PER_SCENE_TTS_QUOTA",
        re.compile(r"One request per scene"),
        "TTS requests are transport chunks packed at sentence "
        "boundaries, never a per-scene quota",
    ),
    (
        "OBSOLETE_SEQUENTIAL_TTS",
        re.compile(r"Send requests SEQUENTIALLY"),
        "tts.py sends requests concurrently with bounded parallelism",
    ),
    (
        "OBSOLETE_FORCED_PREVIEW",
        re.compile(r"960x540, 15 ?fps|960x540/15 ?fps|960x540 at 15 ?fps for previews"),
        "the forced 960x540/15fps preview; previews preserve the "
        "composition aspect at full fps, reduced-fps artifacts are "
        "labeled rough_layout_only (MG-024)",
    ),
    (
        "OBSOLETE_CRITIQUE_MINIMUM_ROUNDS",
        re.compile(r"minimum 3 rounds|at least 3 rounds"),
        "the legacy three-round critique minimum; the shipped rubric "
        "has no minimum round count and a five-round cap (MG-033)",
    ),
    (
        "OBSOLETE_CRITIQUE_SCORE_8",
        re.compile(r"every\s+score\s+(?:is\s+)?8\s+or\s+higher"),
        "the legacy score-8 ship rule; the shipped release gate "
        "requires 9 or higher on every applicable dimension (MG-033)",
    ),
    (
        "OBSOLETE_TWO_HOUR_SCALABILITY",
        re.compile(r"30 seconds to 2 hours|scale from 30 seconds to 2 hours"),
        "the two-hour scalability promise for scene manifests",
    ),
    (
        "OBSOLETE_V1_AS_THE_SKILL",
        re.compile(r"home of the deterministic motion-graphics video pipeline proven"),
        "the V1 __setTime pipeline described as the skill itself; "
        "the shipped system is the two-renderer governed pipeline",
    ),
    (
        "OBSOLETE_MANDATORY_VOICE_INSTALL",
        re.compile(r"Voiceover cannot run without it"),
        "voiceover presented as an install prerequisite; silent "
        "jobs need no TTS key and narration exists only where the "
        "mode and brief require it (MG-023)",
    ),
    (
        "OBSOLETE_VENDOR_BAN",
        re.compile(r"Anthropic (models are|is) (banned|prohibited|forbidden)|No Anthropic models in (the )?(Skill 72|this pipeline)"),
        "a blanket authoring-model vendor ban; no vendor is banned "
        "or prescribed (MG-002)",
    ),
    (
        "OBSOLETE_FIXED_RENDER_TIME",
        re.compile(r"renders? in exactly \d+ (seconds|minutes)|fixed render time of \d+"),
        "a fixed render-time promise; performance is reported from "
        "measured benchmarks with their conditions (MG-045)",
    ),
    (
        "OBSOLETE_ENGINE_UNTESTED",
        re.compile(r"(Hyperframes|Remotion)[^\n]{0,40}untested"),
        "a production engine described as untested; both adapters "
        "are implemented, registered, and readiness-proven by record",
    ),
    (
        "OBSOLETE_HYPERFRAMES_UNIMPLEMENTED",
        re.compile(r"The Hyperframes adapter is specified by the same adapter contract"),
        "the Hyperframes adapter described as specification-only; "
        "it is implemented and registered with the dispatcher",
    ),
    (
        "OBSOLETE_AUDIO_LANDS_LATER",
        re.compile(r"lands with the audio implementation items"),
        "the V2 narration path described as unlanded; the MG-023 "
        "audio policy and the stage 6 measurement flow are shipped",
    ),
    (
        "OBSOLETE_CATALOG_C05_ONLY",
        re.compile(r"today: C05|Only C05 is available for production"),
        "the catalog described as C05-only; C04 through C09 are "
        "registered available and C01-C03, C10-C12 carry explicit "
        "unavailable reasons",
    ),
]

EM_DASH = "\u2014"


# Installed third-party content and build output are not authored
# text; this check governs authored files only. A node_modules
# segment marks installed dependencies, a dist segment marks the
# runtime build output, and a .runtime segment marks the runtime
# install tree, wherever any of them appears under the skill root.
EXCLUDED_SEGMENTS = {"node_modules", "dist", ".runtime"}


def reconciled_files(skill_root: Path, repo_root: Path) -> list[Path]:
    files = sorted(
        p
        for p in skill_root.rglob("*.md")
        if "tests/fixtures" not in p.as_posix()
        and "tests/evidence" not in p.as_posix()
        and not EXCLUDED_SEGMENTS.intersection(p.relative_to(skill_root).parts)
    )
    files.append(skill_root / "repo-integration" / "skill-department-map-entry.json")
    for rel in EXTRA_RECONCILED:
        files.append(repo_root / rel)
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="Skill 72 directory (default: this script's parent's parent)")
    args = ap.parse_args()
    skill_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    repo_root = skill_root.parent
    findings: list[str] = []

    texts: dict[Path, str] = {}
    for p in reconciled_files(skill_root, repo_root):
        if not p.exists():
            findings.append(f"MISSING_RECONCILED_FILE {p.relative_to(repo_root)}")
            continue
        texts[p] = p.read_text(errors="ignore")

    # 1. Dead paths from entrypoint and authority documents.
    for rel in ENTRYPOINT_DOCS:
        doc = skill_root / rel
        if doc not in texts:
            continue
        for token in re.findall(r"`([^`\n]+)`", texts[doc]):
            token = token.strip()
            if "<" in token or ">" in token or token.startswith("~") or token.startswith("$"):
                continue
            if ".runtime/" in token:
                # Generated provisioning state, gitignored by design;
                # its absence in a fresh checkout is not a dead path.
                continue
            if not token.startswith(PATH_PREFIXES):
                continue
            target = token.split(" ")[0]
            candidates = [skill_root / target, repo_root / target]
            if target.startswith("72-motion-video-plus/"):
                candidates = [repo_root / target]
            if not any(c.exists() for c in candidates):
                findings.append(f"DEAD_PATH {rel} names {target}, which does not exist")

    # 2. Obsolete promises anywhere in the reconciled set.
    for p, text in texts.items():
        for name, rx, reason in OBSOLETE:
            for m in rx.finditer(text):
                line = text[: m.start()].count("\n") + 1
                findings.append(
                    f"{name} {p.relative_to(repo_root)}:{line}: {reason}"
                )
        if EM_DASH in text and p.is_relative_to(skill_root):
            # The no-em-dash rule is Skill 72's own authored-text rule
            # (QC.md, verify.sh). Other skills' files are scanned for
            # obsolete Skill 72 claims only, not restyled.
            findings.append(f"EM_DASH {p.relative_to(repo_root)}: authored text carries no em dashes")

    # 3a. Status-and-delivery pointer in both entrypoints and the map.
    for rel in ("SKILL.md", "INSTRUCTIONS.md", "references/authority-map.md"):
        if "references/status-and-delivery.md" not in texts.get(skill_root / rel, ""):
            findings.append(
                f"MISSING_STATUS_POINTER {rel} does not point readers to references/status-and-delivery.md"
            )

    # 3b. Four modes named in the entrypoints, the map, and the master contract.
    for rel in ("SKILL.md", "INSTRUCTIONS.md", "MASTERDOC.md", "references/authority-map.md"):
        text = texts.get(skill_root / rel, "")
        for mode in FOUR_MODES:
            if mode not in text:
                findings.append(f"MISSING_MODE {rel} does not name mode {mode}")

    # 3c. Authority map covers the shipped layer references.
    authority = texts.get(skill_root / "references/authority-map.md", "")
    for ref in (
        "references/approvals-and-gates.md",
        "references/preview-and-review.md",
        "references/review-evidence.md",
        "references/technical-qc.md",
        "references/audio-policy.md",
        "references/powerpoint-packaging.md",
        "references/vsl-desktop-handoff.md",
        "references/vsl-mobile-handoff.md",
        "references/integration-contracts.md",
        "references/design-intelligence-bridge.md",
        "references/install-and-migration.md",
        "references/component-catalog.md",
    ):
        if ref not in authority:
            findings.append(f"AUTHORITY_MAP_GAP references/authority-map.md does not list {ref}")

    # 3d. Critique protocol audio evidence points at the shipped QC records.
    critique = texts.get(skill_root / "references/critique-protocol.md", "")
    if "MG-034" not in critique or "final-qc" not in critique:
        findings.append(
            "STALE_AUDIO_EVIDENCE references/critique-protocol.md does not point audio evidence at the MG-034 final QC record"
        )

    # 3e. PowerPoint playback honesty: any reconciled Skill 72 document
    # that discusses PowerPoint playback must state it is UNVERIFIED.
    for p, text in texts.items():
        if p.is_relative_to(repo_root / "47-movie-producer") or p.is_relative_to(
            repo_root / "45-design-intelligence-library"
        ):
            continue
        if "PowerPoint" in text and "playback" in text.lower() and "UNVERIFIED" not in text:
            findings.append(
                f"PLAYBACK_CLAIM {p.relative_to(repo_root)} discusses PowerPoint playback without stating it is UNVERIFIED"
            )

    # 4. Department-map mirror consistency.
    entry_path = skill_root / "repo-integration" / "skill-department-map-entry.json"
    map_path = repo_root / "23-ai-workforce-blueprint" / "skill-department-map.json"
    try:
        entry = json.loads(entry_path.read_text())
        dept_map = json.loads(map_path.read_text())
        canonical = [s for s in dept_map["skills"] if str(s.get("skill")) == "72"]
        if len(canonical) != 1:
            findings.append("MAP_MIRROR the canonical department map does not carry exactly one Skill 72 entry")
        elif canonical[0] != entry:
            findings.append(
                "MAP_MIRROR repo-integration/skill-department-map-entry.json differs from the canonical skill-department-map.json Skill 72 entry"
            )
        desc = entry.get("description", "")
        for word in ("PowerPoint", "VSL", "standalone"):
            if word not in desc:
                findings.append(f"MAP_DESCRIPTION the Skill 72 map description does not mention {word}")
    except Exception as exc:  # noqa: BLE001
        findings.append(f"MAP_MIRROR could not compare the department-map mirrors: {exc}")

    if findings:
        print("AUTHORITY CHECK FAIL")
        for f in findings:
            print(f"[FAIL] {f}")
        print(f"{len(findings)} finding(s)")
        return 1
    print("AUTHORITY CHECK PASS")
    print(
        "checked: dead paths in %d entrypoint docs; obsolete promises, mode and "
        "status presences, playback honesty, and map mirrors across %d reconciled files"
        % (len(ENTRYPOINT_DOCS), len(texts))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
