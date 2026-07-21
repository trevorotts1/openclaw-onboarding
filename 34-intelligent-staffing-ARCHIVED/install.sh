#!/usr/bin/env bash
# ============================================================
# Skill 34: Intelligent Workspace Staffing -- ARCHIVED, REFUSES TO RUN
#
# This installer ran a 102-question interview across a fixed set of seventeen
# departments and wrote specialist classifications, persona assignments and
# package tiers back into role files. Skill 23 (AI Workforce Blueprint) does all
# three inline during its own build, against the departments the owner interview
# actually produced. It also required Skill 33, which is archived too.
#
# Running this stamps classifications onto roles Skill 23 has already classified
# and creates specialist workspaces no Skill 23 build state knows about. So it
# refuses, loudly, with a non-zero exit -- rather than succeeding at the wrong
# thing.
#
# The implementation was removed deliberately, not lost: it is in git history,
# and every capability it had is mapped in ARCHIVED.md and SKILL.md in this
# folder. Do not restore it. Do not remove this refusal.
# ============================================================
set -u

cat >&2 <<'TOMBSTONE'

  ============================================================
   REFUSED -- Skill 34 (Intelligent Staffing) is ARCHIVED
  ============================================================

  This installer must not be run. Skill 23 already performs the
  classification, persona alignment and tiering this asked for.

  Successor: Skill 23 -- AI Workforce Blueprint
             23-ai-workforce-blueprint/INSTALL.md

  Capability map: 34-intelligent-staffing-ARCHIVED/ARCHIVED.md

TOMBSTONE

exit 1
