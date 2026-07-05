# Skill 42 — INSTRUCTIONS (Runtime Guide)

How the agent selects, materializes, and runs a Personal Assistant specialist at runtime.

---

## 1. Selecting which specialist to deploy

Each specialist's `ROSTER.md` declares its **summon conditions** -- the situations in which that specialist activates and what it does. To select:

1. Read `specialists/_index.md` for the full roster and what each specialist owns.
2. Match the owner's request to a specialist's `ROSTER.md` summon conditions.
3. If the request spans multiple specialists (e.g. "plan my week" → Daily Briefing + Task Priority + Calendar), deploy the primary owner first and let it delegate via its `how-to.md`.
4. If no specialist clearly matches, ask the owner a single clarifying question -- do not guess.

Do **not** deploy all 29 at once by default. Materialize on demand: deploy the specialist(s) the owner actually needs, when they need them.

## 2. Materializing a specialist into the owner's workspace

A specialist in `specialists/<slug>/` is a **template**. To put it into service, materialize it into the owner's workspace -- mirroring how Skill 23 builds department workspaces:

**Target path:**
- Mac: `~/.openclaw/workspace/departments/personal-assistant/<slug>/`
- VPS: `/data/.openclaw/workspace/departments/personal-assistant/<slug>/`

**Steps:**
1. Copy the chosen `specialists/<slug>/` folder (all role files + the `SOP/` folder) into the target path. (Specialist 19 ships 12 role files, not 6 — copy the whole folder.)
2. Fill placeholders (see §3), then run the **post-materialization residual scan** (§3) — it exits 1 if any owner-data placeholder went unfilled. Do not proceed with a failing scan.
3. Run the **mandatory closing Command Center converge** (fail-soft):
   ```bash
   bash <skills>/32-command-center-setup/scripts/sync-extensions.sh --converge
   ```
   This registers the specialist's routing and workspace with the Command Center. If Skill 32 is not installed, skip it (fail-soft) — see INSTALL.md §3. A materialized specialist that never converges is invisible to the Command Center; never skip this when Skill 32 is present.
4. If the specialist is to run full-time as its own agent, add an `openclaw.json` agent entry following Skill 23's `add_agent_to_config()` pattern (see INSTALL.md). Most PA specialists run as on-demand sub-roles of the main agent and do NOT need their own agent entry.

## 3. Placeholder substitution

Every shipped file uses `{{TOKEN}}`-style placeholders only -- no real names, emails, or paths. There are **two classes** of placeholder:

- **Owner-data placeholders (fill at materialization)** — substituted once, from the owner's interview answers / USER.md. These MUST all be filled; the residual scan (below) fails on any survivor.
- **Runtime output-template slots (leave in place)** — filled by the specialist *each time it runs* (e.g. inside a briefing or pulse example: `{{PERCENT}}`, `{{COUNT}}`, `{{HOURS}}`, `{{WIN_1}}`, `{{WHY_IT_MATTERS}}`, `{{TREND_ARROW}}`, `{{FACTOR}}`, `{{ACTION}}`, `{{OBSERVATION}}`, `{{ACTIVITY_1}}`, `{{GOAL_NAME}}`, `{{DATE}}`/`{{ISO_DATE}}`/`{{YEAR}}`/`{{MONTH}}`/`{{WEEK}}`, `{{DAILY}}`/`{{WEEKLY}}`/`{{MONTHLY}}`, `{{RECOMMENDATION}}`, `{{VERBATIM_QUOTE}}`, and similar output slots). Do NOT substitute these at install time — they are part of the output format the specialist emits at runtime.

#### Owner-data placeholders (substitute at materialization)

| Placeholder | Source |
|---|---|
| `{{OWNER_NAME}}` / `{{OWNER}}` / `{{NAME}}` | Owner's name |
| `{{TOKEN}}` | Generic owner placeholder in SOP headers ("Owner: {{TOKEN}}") — resolves to `{{OWNER_NAME}}` |
| `{{OWNER_EMAIL}}` | Owner's primary email (pointer) |
| `{{OWNER_TIMEZONE}}` | Owner's timezone |
| `{{ROLE_TITLE}}` | The specialist's role title |
| `{{COMMUNICATION_STYLE}}` | Owner's preferred tone |
| `{{COMPANY_NAME}}` / `{{CLIENT_NAME}}` / `{{CLIENT_NAME_2}}` | Owner's company |
| `{{COMPANY_INDUSTRY}}` / `{{INDUSTRY_VERTICAL}}` | Owner's industry |
| `{{DEPARTMENT_SLUG}}` | Department slug (`personal-assistant`) |
| `{{GENERATION_DATE}}` | Materialization date (today) |
| `{{WORKSPACE_PATH}}` / `{{COMPANY_LIBRARY_PATH}}` | Owner's workspace root (`~/.openclaw/workspace` or `/data/.openclaw/workspace`) |
| `{{INBOX_TOOL}}` / `{{EMAIL_TOOL}}` | Owner's email tool (Gmail, Outlook, …) |
| `{{CALENDAR_TOOL}}` | Owner's calendar tool |
| `{{TASK_TOOL}}` | Owner's task/todo tool (highest-frequency token — 200+ uses) |
| `{{DOCS_TOOL}}` / `{{DOCUMENT_TOOL}}` | Owner's docs tool |
| `{{MESSAGING_TOOL}}` / `{{COMMUNICATION_TOOL}}` | Owner's messaging tool |
| `{{CRM_TOOL}}` | Owner's CRM |
| `{{JOURNAL_TOOL}}` / `{{NOTES_TOOL}}` | Owner's journal/notes tool |
| `{{SEARCH_TOOL}}` / `{{DEEP_SEARCH_TOOL}}` | Owner's research/search tool |
| `{{RECORDING_TOOL}}` / `{{ZOOM_TOOL}}` / `{{VIDEO_TOOL}}` | Meeting-recording / video tool |
| `{{FINANCIAL_TOOL}}` / `{{METRICS_DASHBOARD}}` | Owner's finance/metrics tool |
| `{{BOOK_PERSONA_MATRIX}}` / `{{ASSIGNED_PERSONA}}` / `{{ASSIGNED_PERSONA_VERSION}}` | Skill 22 persona integration (see §5; graceful-degrade if Skill 22 absent) |
| `{{COACH_NAME}}` / `{{THERAPIST_NAME}}` | Named coaching/support persona (owner's choice) |
| `{{CRISIS_LINE}}` | Region-appropriate crisis line (defaults to the public resources in SKILL.md Scope & Safety) |
| `{{OWNER_RECOVERY_EMAIL}}` / `{{PAYMENT_CARD_REF}}` / `{{CREDIT_CARD_1}}` / `{{BANK_NAME_1}}` / `{{PRIMARY_CHECKING}}` / `{{KEYCHAIN_ACCOUNT}}` / … | Life-Admin & Personal-Finance specialist fields — **pointers/labels only, NEVER the actual secret**. The Life-Admin (14) and Personal-Finance (11) specialists carry a long tail of account/subscription/utility label tokens; fill from the owner's own records at deploy time. |

This is the owner-data inventory; the full raw token list lives in the specialist files. Any token above must be filled or the residual scan (below) fails.

The generic `{{TOKEN}}` placeholder used in SOP headers ("Owner: {{TOKEN}}") resolves to `{{OWNER_NAME}}`.

Leave any placeholder unfilled (and flag the gap to the owner) rather than fabricating a value. NEVER substitute one client's data into another client's workspace.

#### Post-materialization residual scan (required)

After filling, run the residual scan in INSTALL.md §3. It greps the materialized copy for
any surviving **owner-data** placeholder and **exits 1** on a hit (runtime output slots are
exempt — they are not in the owner-data set). A clean scan (exit 0) is the gate for
"materialization complete." Then run the closing Command Center converge (§2 step 3).

## 4. The `00-START-HERE.md` read order (per specialist)

When you deploy a specialist, read its files in this order before acting:
1. `00-START-HERE.md` -- orientation
2. `IDENTITY.md` -- the role, mandate, boundaries
3. `SOUL.md` -- the voice/tone
4. `governing-personas.md` -- persona alignment
5. `how-to.md` -- the operating playbook
6. `ROSTER.md` -- summon conditions
7. `SOP/00-INDEX.md` then the relevant `PA-NN-NN.md` for the task at hand

## 5. Persona integration with Skill 22

Each specialist's `governing-personas.md` describes a 5-layer persona alignment that integrates with Skill 22's persona library. At runtime:

- If Skill 22 is installed, read the owner's persona files from `{{WORKSPACE_PATH}}/personas/` and align the specialist's voice to them.
- If Skill 22 is NOT installed, the specialist degrades gracefully: `governing-personas.md` is self-contained enough to run on its own. Do not block deployment on Skill 22.

## 6. Coaching-scope safety (specialists 09, 24, 26)

These specialists are coaching-scope ONLY -- not therapy, medical advice, or crisis intervention. Their SOPs carry STOP-and-refer rules. At runtime, if the owner expresses suicidal ideation, self-harm intent, or acute crisis, STOP the coaching flow and route to the crisis resources named in the SOP (988, NAMI, National DV Hotline). Never improvise past the boundary.

## 7. Logging deployment

Once a specialist is materialized, append one progress line to MEMORY.md (see CORE_UPDATES.md):

```
PA Library: [N] specialist(s) active | deployed: [slug] | Skill 42
```
