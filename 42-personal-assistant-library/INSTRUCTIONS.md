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
1. Copy the chosen `specialists/<slug>/` folder (all 6 role files + the `SOP/` folder) into the target path.
2. Fill placeholders (see §3).
3. If the specialist is to run full-time as its own agent, add an `openclaw.json` agent entry following Skill 23's `add_agent_to_config()` pattern (see INSTALL.md). Most PA specialists run as on-demand sub-roles of the main agent and do NOT need their own agent entry.

## 3. Placeholder substitution

Every shipped file uses `{{TOKEN}}`-style placeholders only -- no real names, emails, or paths. On materialization, substitute from the owner's interview answers / USER.md:

| Placeholder | Source |
|---|---|
| `{{OWNER_NAME}}` | Owner's name |
| `{{COMPANY_NAME}}` | Owner's company |
| `{{COMPANY_INDUSTRY}}` | Owner's industry |
| `{{GENERATION_DATE}}` | Today's date |
| `{{INBOX_TOOL}}` | The owner's email tool (Gmail, Outlook, etc.) |
| `{{WORKSPACE_PATH}}` | Owner's workspace root (`~/.openclaw/workspace` or `/data/.openclaw/workspace`) |
| `{{COMMUNICATION_STYLE}}` | Owner's preferred tone |
| `{{OWNER_EMAIL}}` / `{{OWNER_RECOVERY_EMAIL}}` / `{{PAYMENT_CARD_REF}}` | Life-Admin specialist fields -- pointers only, NEVER the actual secret |

The generic `{{TOKEN}}` placeholder used in SOP headers ("Owner: {{TOKEN}}") resolves to `{{OWNER_NAME}}`.

Leave any placeholder unfilled (and flag the gap to the owner) rather than fabricating a value. NEVER substitute one client's data into another client's workspace.

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
