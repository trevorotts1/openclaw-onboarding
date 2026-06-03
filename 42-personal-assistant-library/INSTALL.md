# Skill 42 — INSTALL (One-Time Setup)

The skill folder ships with the onboarding package -- `install.sh` / `update-skills.sh` copy every `NN-slug/` folder verbatim, so `42-personal-assistant-library/` lands at:
- Mac: `~/.openclaw/skills/42-personal-assistant-library/`
- VPS: `/data/.openclaw/skills/42-personal-assistant-library/`

No separate download step. This file covers prerequisites, verification, and the materialization workflow.

---

## 1. Prerequisites

| Requirement | Status | Why |
|---|---|---|
| Skill 23 (AI Workforce Blueprint) installed | **Required** | PA is a department-level extension; materialization mirrors Skill 23's department-workspace build |
| Skill 22 (Book-to-Persona) installed | **Recommended** | Persona integration in each `governing-personas.md`. Graceful degradation supported -- the skill runs without it |
| Owner interview answers / USER.md present | **Required for materialization** | Source for placeholder substitution |

## 2. Verify the skill landed

```bash
# Mac
bash ~/.openclaw/skills/42-personal-assistant-library/scripts/verify-pa-install.sh
# VPS
bash /data/.openclaw/skills/42-personal-assistant-library/scripts/verify-pa-install.sh
```

This checks all 29 specialist folders, each specialist's 6 role files, and that each `SOP/` folder has `00-INDEX.md` plus at least one `PA-NN-NN.md`. Exit 0 = pass.

For the full install QC (Mac vs VPS path resolution, skill 22/23 presence warnings), run:

```bash
bash ~/.openclaw/skills/42-personal-assistant-library/qc-personal-assistant-library.sh
```

## 3. Materialize a specialist (on demand)

PA specialists are deployed when the owner needs them -- not all at once. To put one into service:

```bash
SLUG="01-inbox-manager"   # the specialist to deploy
SKILL_DIR="$HOME/.openclaw/skills/42-personal-assistant-library"      # Mac
WS="$HOME/.openclaw/workspace"                                        # Mac
# VPS: SKILL_DIR=/data/.openclaw/skills/...  WS=/data/.openclaw/workspace

mkdir -p "$WS/departments/personal-assistant"
cp -r "$SKILL_DIR/specialists/$SLUG" "$WS/departments/personal-assistant/$SLUG"
```

Then fill placeholders in the copied folder (see INSTRUCTIONS.md §3). A minimal fill pass:

```bash
DEST="$WS/departments/personal-assistant/$SLUG"
# Example substitutions — pull real values from USER.md / interview answers.
# NEVER hardcode another client's data. Leave a placeholder unfilled rather than guess.
find "$DEST" -type f -name '*.md' -print0 | while IFS= read -r -d '' f; do
  sed -i '' \
    -e "s/{{OWNER_NAME}}/$OWNER_NAME/g" \
    -e "s/{{TOKEN}}/$OWNER_NAME/g" \
    "$f"   # GNU sed (VPS): use `sed -i` without the '' argument
done
```

## 4. Optional: run a specialist full-time as its own agent

Most PA specialists run as on-demand sub-roles of the main agent. If the owner wants one to run full-time (e.g. an always-on Inbox Manager), add an agent entry to `openclaw.json` following Skill 23's `add_agent_to_config()` pattern -- same shape Skill 23 uses for business departments. See `23-ai-workforce-blueprint/scripts/` for the canonical helper.

## 5. Optional: auto-build for every client (Skill 23 naming-map patch)

To make Skill 23 auto-build the PA department for every new client, add `personal-assistant` to the `mandatory` block of `23-ai-workforce-blueprint/department-naming-map.json` and remove the pending-proposal TODO. This is a **product decision** -- confirm before applying. It is intentionally NOT part of this skill's first ship. Without it, Skill 23 can still reference the PA library via Option C (Audit/Resume) once this skill is installed.

## 6. Core file updates

After install, apply the appends in CORE_UPDATES.md to the workspace's AGENTS.md, TOOLS.md, and MEMORY.md.
