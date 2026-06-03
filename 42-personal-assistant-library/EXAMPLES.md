# Skill 42 — EXAMPLES (Worked Flows)

Universal placeholders only. No real client data.

---

## Example 1 — Owner asks: "Set up my inbox manager"

1. Match to `specialists/01-inbox-manager/ROSTER.md` summon conditions.
2. Materialize:
   ```bash
   cp -r ~/.openclaw/skills/42-personal-assistant-library/specialists/01-inbox-manager \
         ~/.openclaw/workspace/departments/personal-assistant/01-inbox-manager
   ```
3. Fill placeholders from USER.md: `{{OWNER_NAME}}`, `{{INBOX_TOOL}}` (e.g. Gmail), `{{COMMUNICATION_STYLE}}`, `{{WORKSPACE_PATH}}`.
4. Read `01-inbox-manager/00-START-HERE.md` → IDENTITY → SOUL → governing-personas → how-to → ROSTER → `SOP/00-INDEX.md`.
5. Run `PA-01-01` (triage) on the owner's first inbox pass.
6. Append to MEMORY.md: `PA Library: 1 specialist(s) active | deployed: 01-inbox-manager | Skill 42`.

## Example 2 — Owner asks: "Help me plan my week"

A multi-specialist request. Deploy the primary owner and delegate:
1. Daily Briefing & Debrief (`03`) → run `PA-03-03-Weekly-Preview`.
2. It pulls from Task & Priority Manager (`04`, daily top-3) and Calendar (`02`, focus-block protection).
3. Materialize 03, 04, 02 if not already present; fill placeholders; run their weekly SOPs in order.

## Example 3 — Owner says something that signals crisis during a coaching session

Specialist 09 / 24 / 26 are coaching-scope ONLY. If the owner expresses suicidal ideation, self-harm intent, or acute crisis:
1. STOP the coaching flow immediately.
2. Route per the SOP's crisis-referral block: 988 (call or text), Therapy for Black Girls (therapyforblackgirls.com), NAMI Helpline (1-800-950-6264), National DV Hotline (1-800-799-7233).
3. Do not attempt therapy or improvise past the boundary.

## Example 4 — Owner asks: "I want a coach"

1. Match to `08-my-coach/ROSTER.md`.
2. Materialize `08-my-coach`, fill `{{OWNER_NAME}}` / `{{COMMUNICATION_STYLE}}`.
3. Run `PA-08-03-goal-setting-session`, then schedule `PA-08-06-weekly-accountability-review` via the Calendar specialist.

## Example 5 — Persona alignment with Skill 22

If Skill 22 is installed, when deploying any specialist read `{{WORKSPACE_PATH}}/personas/` and align the specialist's `SOUL.md` voice to the owner's persona. If Skill 22 is absent, the specialist's `governing-personas.md` is self-contained -- proceed without blocking.
