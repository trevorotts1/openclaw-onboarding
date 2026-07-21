#!/usr/bin/env bash
# ============================================================
# Skill 33: Permanent Department Heads -- ARCHIVED, REFUSES TO RUN
#
# This installer created 17 fixed department workspaces and added 17 entries to
# agents.list[] in ~/.openclaw/openclaw.json. Skill 23 (AI Workforce Blueprint)
# absorbed all of it and builds the workforce from the owner interview instead.
#
# Running this against a box Skill 23 has already built produces duplicate and
# conflicting registry entries plus department workspaces no Skill 23 build state
# knows about. So it refuses, loudly, with a non-zero exit -- rather than
# succeeding at the wrong thing.
#
# The implementation was removed deliberately, not lost: it is in git history,
# and every capability it had is mapped in ARCHIVED.md and SKILL.md in this
# folder. Do not restore it. Do not remove this refusal.
# ============================================================
set -u

cat >&2 <<'TOMBSTONE'

  ============================================================
   REFUSED -- Skill 33 (Permanent Department Heads) is ARCHIVED
  ============================================================

  This installer must not be run. It writes the superseded
  seventeen-department model into a live workforce.

  Successor: Skill 23 -- AI Workforce Blueprint
             23-ai-workforce-blueprint/INSTALL.md

  Capability map: 33-department-heads-ARCHIVED/ARCHIVED.md

TOMBSTONE

exit 1
