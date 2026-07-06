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

Then fill placeholders in the copied folder (see INSTRUCTIONS.md §3 for the full
placeholder table). Substitute the **owner-data** placeholders — runtime output-template
slots (`{{PERCENT}}`, `{{WIN_1}}`, `{{TREND_ARROW}}`, `{{COUNT}}`, …) are filled by the
specialist each run and are left in place. A fill pass over the core owner tokens:

```bash
DEST="$WS/departments/personal-assistant/$SLUG"
# Pull real values from USER.md / interview answers. NEVER hardcode another client's data.
# Leave a placeholder unfilled rather than guess — the residual scan below flags gaps.
# The generic {{TOKEN}} owner placeholder resolves to the owner's name.
GENERATION_DATE="${GENERATION_DATE:-$(date +%F)}"
WORKSPACE_PATH="$WS"
S="sed -i ''"          # macOS/BSD sed
# GNU sed (VPS): S="sed -i"   (no '' argument)
find "$DEST" -type f -name '*.md' -print0 | while IFS= read -r -d '' f; do
  $S \
    -e "s|{{OWNER_NAME}}|$OWNER_NAME|g" \
    -e "s|{{TOKEN}}|$OWNER_NAME|g" \
    -e "s|{{OWNER_EMAIL}}|$OWNER_EMAIL|g" \
    -e "s|{{OWNER_TIMEZONE}}|$OWNER_TIMEZONE|g" \
    -e "s|{{ROLE_TITLE}}|$ROLE_TITLE|g" \
    -e "s|{{COMMUNICATION_STYLE}}|$COMMUNICATION_STYLE|g" \
    -e "s|{{COMPANY_NAME}}|$COMPANY_NAME|g" \
    -e "s|{{COMPANY_INDUSTRY}}|$COMPANY_INDUSTRY|g" \
    -e "s|{{GENERATION_DATE}}|$GENERATION_DATE|g" \
    -e "s|{{WORKSPACE_PATH}}|$WORKSPACE_PATH|g" \
    -e "s|{{INBOX_TOOL}}|$INBOX_TOOL|g" \
    -e "s|{{CALENDAR_TOOL}}|$CALENDAR_TOOL|g" \
    -e "s|{{TASK_TOOL}}|$TASK_TOOL|g" \
    -e "s|{{DOCS_TOOL}}|$DOCS_TOOL|g" \
    "$f"
done
# …extend with the remaining owner-data tokens the chosen specialist uses (see the
# full table in INSTRUCTIONS.md §3 — tool, persona, and Life-Admin-pointer tokens).
```

### Post-materialization residual scan (MANDATORY — exits 1 on any unfilled owner placeholder)

After the fill pass, assert that no owner-data placeholder survived. Runtime output-template
slots are exempt by construction (they are not in the owner-data set):

```bash
# Owner-data placeholders the fill pass is responsible for. Keep in sync with
# INSTRUCTIONS.md §3. Runtime slots ({{PERCENT}}/{{WIN_1}}/{{COUNT}}/…) are NOT listed.
INSTALL_PLACEHOLDERS='OWNER_NAME|OWNER|NAME|TOKEN|OWNER_EMAIL|OWNER_RECOVERY_EMAIL|OWNER_TIMEZONE|ROLE_TITLE|COMMUNICATION_STYLE|COMPANY_NAME|CLIENT_NAME|CLIENT_NAME_2|COMPANY_INDUSTRY|INDUSTRY_VERTICAL|DEPARTMENT_SLUG|WORKSPACE_PATH|COMPANY_LIBRARY_PATH|GENERATION_DATE|INBOX_TOOL|EMAIL_TOOL|CALENDAR_TOOL|TASK_TOOL|DOCS_TOOL|DOCUMENT_TOOL|MESSAGING_TOOL|COMMUNICATION_TOOL|CRM_TOOL|JOURNAL_TOOL|SEARCH_TOOL|DEEP_SEARCH_TOOL|NOTES_TOOL|RECORDING_TOOL|ZOOM_TOOL|VIDEO_TOOL|FINANCIAL_TOOL|METRICS_DASHBOARD|BOOK_PERSONA_MATRIX|ASSIGNED_PERSONA|ASSIGNED_PERSONA_VERSION|COACH_NAME|THERAPIST_NAME|CRISIS_LINE'
RESIDUAL="$(grep -rnoE "\{\{(${INSTALL_PLACEHOLDERS})\}\}" "$DEST" || true)"
if [ -n "$RESIDUAL" ]; then
  echo "FAIL: unfilled owner-data placeholders remain in $DEST:" >&2
  echo "$RESIDUAL" >&2
  echo "Fill them from USER.md / interview answers, then re-run this scan." >&2
  exit 1
fi
echo "OK: no unfilled owner-data placeholders in $DEST"
```

### Closing step — Command Center converge (MANDATORY, fail-soft)

Materialization is not complete until the new specialist is converged into the Command
Center (routing + workspace registration) by running `sync-extensions.sh --converge`. This
is fail-soft: if Skill 32 (Command Center) is not installed, it is skipped rather than
blocking the deployment.

```bash
CC_SYNC="$SKILL_DIR/../32-command-center-setup/scripts/sync-extensions.sh"   # sync-extensions.sh --converge
if [ -x "$CC_SYNC" ]; then
  bash "$CC_SYNC" --converge \
    || echo "WARN: CC converge returned non-zero — re-run after resolving the Command Center issue (non-fatal to the copy)."
else
  echo "NOTE: Command Center (Skill 32) not installed — skipping converge (fail-soft)."
fi
```

## 4. Optional: run a specialist full-time as its own agent

Most PA specialists run as on-demand sub-roles of the main agent. If the owner wants one to run full-time (e.g. an always-on Inbox Manager), add an agent entry to `openclaw.json` following Skill 23's `add_agent_to_config()` pattern -- same shape Skill 23 uses for business departments. See `23-ai-workforce-blueprint/scripts/` for the canonical helper.

## 5. Auto-build for every client (already mandatory in Skill 23)

As of Skill 23 v10.15.42, `personal-assistant` is in the **mandatory** block of `23-ai-workforce-blueprint/department-naming-map.json` (universal floor raised to 24). Skill 23 therefore **auto-builds the Personal Assistant department for every new client** as a standard-unless-declined department -- no manual naming-map patch is required. Skill 42 supplies the 29 specialist sub-workspaces that populate that department. On a box where the department already exists, Skill 23 can also reference this library via Option C (Audit/Resume).

## 6. Core file updates

After install, apply the appends in CORE_UPDATES.md to the workspace's AGENTS.md, TOOLS.md, and MEMORY.md.
