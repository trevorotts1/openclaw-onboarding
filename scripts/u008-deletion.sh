#!/bin/bash
# U008 Phase 2 — Deletion Script
# Removes 22 NN-<slug> directories from the live department.
# Uses mv (not rm) so the step is reversible in place.
# Names all 22 directories literally — no glob, no loop over ls.
# Must be run AFTER U003's backup is re-verified.
set -euo pipefail

BK="${BK:-}"
DEPT="/Users/blackceomacmini/.openclaw/workspace/departments/Presentations"
UTC_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RETIRED="${DEPT}/working/u008-retired-${UTC_STAMP}"
MERGED_ROOT="${MERGED_ROOT:-}"

# ---- Gate 0: verify the U003 backup checksum ----
if [ -z "${BK:-}" ] || [ ! -f "${BK}/Presentations-FULL.tar.gz.sha256" ]; then
    echo "FATAL: BK is not set or does not point to a valid U003 archive. Set BK explicitly." >&2
    exit 1
fi
( cd "${BK}" && shasum -a 256 -c Presentations-FULL.tar.gz.sha256 ) || {
    echo "FATAL: backup checksum verification FAILED. STOP." >&2
    exit 1
}
echo "[gate-0] backup checksum VERIFIED: ${BK}"

# ---- Gate 1: create retirement directory ----
mkdir -p "${RETIRED}"

# ---- Gate 2: write merged content into surviving bare directories BEFORE moving numbered ones ----
if [ -n "${MERGED_ROOT:-}" ] && [ -d "${MERGED_ROOT}" ]; then
    echo "[gate-2] writing merged content into surviving bare directories..."
    while IFS= read -r slug; do
        MERGED_DIR="${MERGED_ROOT}/${slug}"
        TARGET_DIR="${DEPT}/${slug}"
        if [ -d "${MERGED_DIR}" ] && [ -d "${TARGET_DIR}" ]; then
            for f in "${MERGED_DIR}"/*; do
                fname=$(basename "${f}")
                cp "${f}" "${TARGET_DIR}/${fname}"
            done
        fi
    done <<'SLUGS'
audio-demonstration-specialist
brainstorming-buddy-presentations
brand-steward
capacity-reliability-engineer
deep-research-specialist-presentations
delivery-concierge
devils-advocate-presentations
director-of-presentations
first-time-onboarding-presentations
healer-presentations
hook-strategist
media-librarian-ghl-updater
offer-price-strategist
pptx-assembly-specialist
presenter-coach
presenters-guide-specialist
presenters-speech-writer
qc-specialist-presentations
slide-copywriter
slide-image-creator
slide-submitter
typography-architect
SLUGS
else
    echo "[gate-2] MERGED_ROOT not set or not found; skipping merge content write"
fi

# ---- Step: count directories BEFORE ----
BEFORE=$(ls -d "${DEPT}"/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "[census] before: ${BEFORE} directories"

# ---- Step: move NUMBERED directories to retirement ----
# Each directory named LITERALLY — no glob, no NN-*, no loop over ls

mv "${DEPT}/21-audio-demonstration-specialist"       "${RETIRED}/21-audio-demonstration-specialist"
mv "${DEPT}/17-brainstorming-buddy-presentations"    "${RETIRED}/17-brainstorming-buddy-presentations"
mv "${DEPT}/04-brand-steward"                        "${RETIRED}/04-brand-steward"
mv "${DEPT}/09-capacity-reliability-engineer"        "${RETIRED}/09-capacity-reliability-engineer"
mv "${DEPT}/10-deep-research-specialist-presentations" "${RETIRED}/10-deep-research-specialist-presentations"
mv "${DEPT}/12-delivery-concierge"                   "${RETIRED}/12-delivery-concierge"
mv "${DEPT}/11-devils-advocate-presentations"        "${RETIRED}/11-devils-advocate-presentations"
mv "${DEPT}/00-director-of-presentations"            "${RETIRED}/00-director-of-presentations"
mv "${DEPT}/22-first-time-onboarding-presentations"  "${RETIRED}/22-first-time-onboarding-presentations"
mv "${DEPT}/15-healer-presentations"                 "${RETIRED}/15-healer-presentations"
mv "${DEPT}/14-hook-strategist"                      "${RETIRED}/14-hook-strategist"
mv "${DEPT}/07-media-librarian-ghl-updater"           "${RETIRED}/07-media-librarian-ghl-updater"
mv "${DEPT}/02-offer-price-strategist"               "${RETIRED}/02-offer-price-strategist"
mv "${DEPT}/08-pptx-assembly-specialist"             "${RETIRED}/08-pptx-assembly-specialist"
mv "${DEPT}/13-presenter-coach"                      "${RETIRED}/13-presenter-coach"
mv "${DEPT}/19-presenters-guide-specialist"          "${RETIRED}/19-presenters-guide-specialist"
mv "${DEPT}/20-presenters-speech-writer"             "${RETIRED}/20-presenters-speech-writer"
mv "${DEPT}/05-qc-specialist-presentations"          "${RETIRED}/05-qc-specialist-presentations"
mv "${DEPT}/01-slide-copywriter"                     "${RETIRED}/01-slide-copywriter"
mv "${DEPT}/03-slide-image-creator"                  "${RETIRED}/03-slide-image-creator"
mv "${DEPT}/06-slide-submitter"                      "${RETIRED}/06-slide-submitter"
mv "${DEPT}/18-typography-architect"                 "${RETIRED}/18-typography-architect"

echo "[moves] 22 directories moved to ${RETIRED}"

# ---- Step: remove DANGLING symlinks from paired directories ----
# Bare directories (surviving ones): remove only symlinks that do not resolve
# Numbered directories are already moved; their symlinks are gone.
REMOVED=0
SKIPPED=0
while IFS= read -r slug; do
    SURVIVING="${DEPT}/${slug}"
    for linkname in TOOLS.md USER.md; do
        p="${SURVIVING}/${linkname}"
        if [ -L "${p}" ] && ! [ -e "${p}" ]; then
            /bin/unlink "${p}"
            REMOVED=$((REMOVED + 1))
        elif [ -L "${p}" ]; then
            SKIPPED=$((SKIPPED + 1))
        fi
    done 2>/dev/null || true
done <<'SLUGS'
audio-demonstration-specialist
brainstorming-buddy-presentations
brand-steward
capacity-reliability-engineer
deep-research-specialist-presentations
delivery-concierge
devils-advocate-presentations
director-of-presentations
first-time-onboarding-presentations
healer-presentations
hook-strategist
media-librarian-ghl-updater
offer-price-strategist
pptx-assembly-specialist
presenter-coach
presenters-guide-specialist
presenters-speech-writer
qc-specialist-presentations
slide-copywriter
slide-image-creator
slide-submitter
typography-architect
SLUGS

echo "[symlinks] removed ${REMOVED} dangling symlinks, skipped ${SKIPPED} resolving"

# ---- Census AFTER ----
AFTER=$(ls -d "${DEPT}"/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "[census] after: ${AFTER} directories"
echo "[census] delta: $((BEFORE - AFTER)) (expected: 22)"

# ---- Verify the count ----
if [ "${AFTER}" -eq "$((BEFORE - 22))" ]; then
    echo "[DONE] directory census: ${BEFORE} -> ${AFTER} (removed exactly 22)"
else
    echo "FATAL: expected ${BEFORE} -> $((BEFORE - 22)) but got ${AFTER}" >&2
    exit 1
fi
