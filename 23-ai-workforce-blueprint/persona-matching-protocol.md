# Persona Matching Protocol
## How Personas Are Assigned to Agents and Sub-Agents

**Version:** 1.0.0
**Date:** March 27, 2026

---

## Core Principle

**Personas are NOT assigned to departments. Personas are attached to an agent or sub-agent at the task level.**

A persona is chosen fresh for every task based on three alignment layers. The same role in the same department may use different personas depending on what they are trying to accomplish.

> **Which "persona" this document governs.** The word *persona* means three unrelated things across the system. This protocol governs **concept 2 only — the coaching/leadership persona** (the 81-persona `coaching-personas` library matched per task at runtime). It does NOT govern the **`dept_label` / `workspace_hint`** (the department-head display name and the `persona` key in the `/api/tasks/ingest` payload — a routing hint, never a coaching persona) or the **buyer/customer persona (avatar)** used in copy work (Skill 52 avatars, "Big Bold Who" sections). See `TERMINOLOGY.md` → "Persona — three distinct meanings" for the full three-way distinction.

---

## The 5 Alignment Layers

Every time a task is assigned to an agent or sub-agent, the system runs these 5 checks to find the best persona match. All 5 layers matter. No single layer overrides the others.

Layers 1-2 run once at setup to create a pre-qualified pool. Layers 3-5 run fresh for every individual task.

### Layer 1: Company Mission

**Question:** Does this persona align with the company's mission?

**What to check:**
- The company's stated mission (from SOUL.md, interview answers, or company-config.json)
- The persona's core philosophy and methodology
- Whether the persona's approach supports or contradicts what the company stands for

**Example:** A company whose mission is empathetic customer transformation would weight personas like Brene Brown (Atlas of the Heart) higher than a pure growth-hacking persona.

### Layer 2: Owner Values

**Question:** Does this persona match the owner's personal beliefs and style?

**What to check:**
- USER.md -- the owner's identity, background, values, communication style
- Learned preferences from conversations and memory
- Cultural context, personal philosophy, leadership style

**Example:** An African-American female business owner who values authenticity and community would get different persona weighting than a tech startup founder who values speed and disruption, even if both have the same company mission.

### Layer 3: Company Goals/KPIs

**Question:** Does this persona support what the company is trying to achieve right now?

**What to check:**
- The company's current goals and KPIs (from company-config.json or MEMORY.md)
- Whether the persona's methodology directly supports those goals
- The company's current priorities and challenges

**Example:** A company focused on increasing revenue this quarter would weight Hormozi (100M Offers) and Priestley (Oversubscribed) higher than a persona focused on internal culture building.

### Layer 4: Department Goals/KPIs

**Question:** Does this persona fit this department's objectives?

**What to check:**
- The department's stated goals and KPIs (from department-config.json or department's 00-START-HERE.md)
- Whether the persona's strengths align with what this department is measured on
- The department's current priorities

**Example:** A Marketing department focused on email open rates would weight Bly (Copywriter's Handbook) and Wiebe (Copy Hackers) higher than a leadership-focused persona, even if that leadership persona scored well on Layers 1-2.

### Layer 5: Task Fit

**Question:** Is this persona the right guide for THIS specific task?

**What to check:**
- The task description and objective
- The role's core responsibilities (from the role's 00-START-HERE.md)
- The persona's specific strengths and "when to use" guidance
- What this specialist is trying to accomplish right now

**Example:** A Content Creator in the Marketing department might use:
- Donald Miller (StoryBrand) when writing brand messaging
- Brendan Kane (Hook Point) when writing social media hooks
- Robert Bly (Copywriter's Handbook) when writing long-form sales copy

All three are valid for the same role. The task determines which one fits.

---

## How to Run the Match

When a task comes in and needs a persona:

### Step 1: Gather Context
```
- Read the task description
- Read the role's 00-START-HERE.md
- Read the department's 00-START-HERE.md
- Read USER.md and SOUL.md
- Read MEMORY.md for any learned preferences about persona use
```

### Step 2: Query the Persona Collection

**BEFORE running Gemini search, read `persona-categories.json` (located in Skill 22 folder), identify the relevant domain tags for this department, and include those tags in your search query.** This ensures the search is scoped to the right category space rather than returning generic matches.

```
# First: read persona-categories.json to find relevant domain tags for this department
# Then: construct search query with those tags included
gemini search "<task description> + <role purpose> + <user context keywords> + <domain tags from persona-categories.json>" -c coaching-personas
```

This returns the top matching personas ranked by relevance. Including domain tags (e.g., `marketing`, `sales`, `copywriting`) focuses results on personas whose expertise aligns with the department's domain.

### Step 3: Apply the 5 Layers
Score each candidate persona against all 5 layers:
- Layer 1 (Company Mission): Does this persona's philosophy align with the company's mission?
- Layer 2 (Owner Values): Does this persona match the owner's beliefs and style?
- Layer 3 (Company Goals): Does this persona support the company's current goals/KPIs?
- Layer 4 (Department Goals): Does this persona fit this department's objectives/KPIs?
- Layer 5 (Task Fit): Is this persona the right guide for THIS specific task?

Layers 1-2 create the pre-qualified pool (run once at setup). Layers 3-5 run fresh every task.

### Step 4: Select and Log
- Choose the highest-scoring persona
- Log the selection reasoning (which layers influenced the choice and why)
- Attach the persona to the agent/sub-agent for this task
- The persona stays attached for the duration of that task only

**MANDATORY: Before executing any task, write a selection log entry to `persona-selection-log.md` in the department workspace.**

Format:
```
[date] [task-id] [candidates-considered] [selected-persona] [layer-3-reason] [layer-4-reason] [layer-5-reason]
```

Example:
```
2026-04-12 task-0042 "Hormozi, Miller, Kane" "Hormozi" "Revenue KPI alignment" "Marketing conversion goals" "Sales copywriting task"
```

Every task dispatch MUST produce a log entry. No exceptions. This creates an audit trail for persona effectiveness and enables future optimization of the matching algorithm.

### Step 5: Load and Apply the Task Mode (Leadership / Governance side) — MANDATORY

Selecting and naming a persona is NOT the same as being guided by it. A persona blueprint is **dual-purpose**: the Coaching half (Sections 1-3, 6, 7A) shapes how you *talk*; the **Leadership / Task-Mode half** governs how you *build*. For any professional, non-mechanical task the executing agent MUST load and apply the Task-Mode half BEFORE producing the artifact — not just surface the persona's name or voice.

Concrete load step (do this every task, after selection, before execution):

```
1. Resolve the selected persona_id to its blueprint:
   .../coaching-personas/personas/<persona_id>/persona-blueprint.md
   (or retrieve the governance directly: gemini search "<task>" -c coaching-personas --mode leadership)
2. Read the persona's TASK MODE — Section 4 "Agent Governance Framework":
   - 4A Execution Standard + Decision Logic Table   → the rules you make calls by
   - 4B Quality Control Protocol + Definition of Done → the bar the artifact must clear
   - 4C Failure Pattern Recognition                  → the anti-patterns you must avoid
   - 4D Task Mode Activation Language
   ...plus Section 7B Task-Mode Triggers.
3. BUILD TO THAT STANDARD — execute the task through the persona's decision logic, hold their
   quality bar, and produce an artifact that satisfies their Definition of Done.
4. Record what you loaded in the selection log so grounding is provable, e.g.:
   - task_mode_loaded: <persona_id> persona-blueprint.md Section 4
   - execution_standard_applied: <one-line summary of the decision logic used>
   - definition_of_done: <the persona's DoD the artifact was held to>
   - failure_patterns_checked: <the 4C anti-patterns ruled out>
```

The role-library §2 "Persona Governance Override" tells an agent to *act AS* the persona and *hold their standards*; THIS step is HOW it obtains those standards. A role file's §2 is inert without this load step — they are designed to work together.

### Anti-Staleness Guards

MEMORY.md learned preferences are data, NOT shortcuts. Never skip the 5-layer alignment because MEMORY.md says 'usually pick X'.

If persona-selection-log.md shows the same persona chosen 5+ times in a row for the same department, flag for review. Repetition without fresh alignment is staleness.

The full 5-layer check runs fresh EVERY time. No caching. No shortcuts. No 'I already know this one.'

---

## What governing-personas.md Should Contain

The `governing-personas.md` file in each role folder is NOT a static assignment. It is a REFERENCE GUIDE that helps agents make better matches faster.

It should contain:
1. **Available persona pool** -- the full list of personas installed in this system
2. **Suggested starting points** -- personas that commonly work well for this role (as hints, not mandates)
3. **Matching instructions** -- a pointer to this protocol document
4. **Task-type examples** -- "For negotiation tasks, consider Voss. For storytelling tasks, consider Miller."

It should NOT contain:
- "This department uses Persona X" (departments don't use personas; agents do)
- A single assigned persona for the whole department
- Static assignments that never change

---

## Important Distinctions

| Concept | Correct | Incorrect |
|---------|---------|-----------|
| Who gets a persona | An agent or sub-agent | A department |
| When assigned | Per task, at runtime | At build time, permanently |
| How chosen | 5-layer alignment check | Hardcoded in a config file |
| Can it change? | Yes, every task can have a different persona | No, same persona forever |
| Where logged? | Task execution log | Static governing-personas.md |

---

## Edge Cases

**What if the same persona matches for every task in a department?**
That is valid but rare. If it happens, it means that persona is genuinely the best fit for everything that department does. The system should still check every time rather than assuming.

**What if no persona scores well on all 5 layers?**
Pick the one with the strongest Layer 5 (task fit) score. The task must get done well. The other layers are important but should not block execution.

**What if Skill 22 is not installed?**
This is a **DEGRADED** state, **not a valid steady state**. Persona matching cannot run because the coaching-personas library is absent — but an agent MUST NOT execute a professional task with no persona at all. Two things are mandatory while in this state:

1. **Mandatory default-persona attachment (never naked):** attach the default fallback persona — the `blackceo-house-voice` persona, defined as the `DEFAULT_PERSONA_FALLBACK` constant: a general-purpose house voice that is **excluded from normal persona competition** and surfaces **only** as a fallback. Every task still carries an assigned persona; there is no such thing as a persona-less professional task. A purely mechanical task (e.g. `restart`, `ping`, `chmod`) keeps its `no_persona_required` flag but still carries a `governance_persona_id` — the `GOVERNANCE_PERSONA_FALLBACK` constant, `covey-7-habits` — so every downstream gate always has a persona to point at.
2. **Install nag:** surface an operator-visible nag that Skill 22 is not installed and persona matching is degraded, so the library gets installed. Operator-visible only — never client-facing, per the silent-updates doctrine.

When Skill 22 is installed later, full 5-layer persona matching activates automatically and the fallback stops being used. **The absence of the library is a bug signal to remediate, not a licence to run naked.**

---

## Memory Wiki Integration

After every 50 tasks with persona selection, compile a wiki source page summarizing:
- Most-used personas per department
- Task types that consistently match certain personas
- Persona diversity scores

This data helps tune the 5-layer alignment over time.

---

## Post-Task Persona Verification

After completing any task, the agent MUST self-check:

1. **Did my output follow [persona name]'s methodology?**
   - Did I apply their specific frameworks and sequencing?
   - Did I use their decision logic and rules?
   - Did I avoid patterns they explicitly reject?

2. **Did I apply their specific standards?**
   - Did I follow the execution checklist?
   - Did I meet the quality bar defined in the blueprint?
   - Did I check against failure patterns?

3. **Log the self-check result in the task completion report:**
   ```
   [task-id] Persona Verification: [persona-name]
   - Methodology followed: YES / PARTIAL / NO
   - Standards applied: YES / PARTIAL / NO
   - Notes: [any deviations or gaps]
   ```

**Why this matters:** Persona matching is only effective if the selected persona's methodology is actually applied. This self-check creates accountability and provides data for improving persona selection accuracy over time.

**When verification fails:** If the agent realizes the output did NOT follow the persona's methodology, flag it:
- Note the gap in the completion report
- Re-run the task with explicit reference to the persona blueprint
- Log both attempts for pattern analysis

---

## APPENDIX: Skill 59 (Anthology Engine) — Stage-to-Role-to-Persona Matching Table

**Stamped:** W4.2 (Wave 4, Anthology Engine build), per the Anthology Engine
PRD Section 13 (the operator's out-of-tree `Anthology-Engine/PRD.md` planning
doc) and SPEC 6.3.

**Which persona concept this table is.** The "Named persona" column below is
neither concept 1 (`dept_label`/`workspace_hint`), concept 2 (the 81-persona
`coaching-personas` library this whole document governs), nor concept 3 (the
buyer/customer avatar) from the three-way distinction above and in
`TERMINOLOGY.md`. It is a FOURTH, skill-internal kind: a named voice BAKED into
one of Skill 54/59's own sha256-pinned prompt assets (the `aw-*`/`aa-*`/`ae-*`
pin ids), fixed at authoring time, never matched at runtime by the 5-layer
selector, and never derived from a department. This table is a STATIC binding
of pipeline stage to the ROLE that operates it (concept-1-adjacent, a routing
fact) and, where one exists, the persona voice pinned into that stage's prompt.
It sits beside, and is never substituted for, the 5-layer runtime coaching-
persona match this document otherwise governs — a task inside one of these
stages that also needs a coaching persona (e.g. an operator-facing summary)
still runs the full 5-layer alignment above.

Roles: `anthology-chapter-author` (Skill 54's authoring core, pre-existing;
`54-anthology-writer/roles/anthology-writer.role.md`); `anthology-producer-
orchestrator` (new — owns the run end to end, the ledger, the exceptions
queue, escalations, S7 cover, S8 delivery, and S9 assembly machinery;
`59-anthology-engine/roles/anthology-producer-orchestrator.role.md`);
`anthology-approvals-steward` (new — owns gate hygiene, nudge cadence, the
readiness report, the trigger and sign-off flow, and the Gate B content judge;
`59-anthology-engine/roles/anthology-approvals-steward.role.md`).

| Stage | Operating role | Named persona (lives in the pinned prompt) |
|---|---|---|
| S0 intake and routing | anthology-producer-orchestrator | none (deterministic code) |
| S1 avatar | anthology-chapter-author | the Avatar Profiler (Skill 52, pins aa-01 to aa-03) |
| S2 tone | anthology-chapter-author | the Tone Analysts and Blender (tone core 04 to 08) |
| S3 title | anthology-chapter-author | the Senior Title Strategist (aw-06) |
| S4 blurb plus outline | anthology-chapter-author | the Blurb Copywriter (aw-07) and the Outline Architect (aw-08) |
| S5 chapter | anthology-chapter-author | the Anthology Chapter Author (aw-09) |
| S6 rewrite | anthology-chapter-author | Dr. Margaret Thornfield, editorial revisionist (aw-10) |
| S7 cover | anthology-producer-orchestrator | the Senior Book-Cover Design Specialist (aw-11) |
| S8 package and deliver | anthology-producer-orchestrator | none (deterministic rendering and delivery) |
| All gates, nudges, readiness report | anthology-approvals-steward | none (gate logic; sanctioned templates only) |
| S9 assembly | anthology-producer-orchestrator | the Anthology Editor voice (ae-01 to ae-04), subordinate to producer inputs |
| Content QC (Gate B judge) | anthology-approvals-steward | the independent Editorial Judge on the JUDGE tier |

**QC-independence rule (binding, explicit, AF-AE-JUDGE-INDEPENDENCE):** the
Gate B content-QC judge harness NEVER runs the persona OR the model tier that
drafted the piece it is reviewing. Concretely, in `59-anthology-engine/scripts/
judge_harness.py`, `enforce_independence()` refuses (exit 2) whenever the
JUDGE tier, resolution, or persona equals the writer's — the independent
Editorial Judge on the JUDGE tier is, by construction, never the same operator
that spoke the Anthology Chapter Author, Dr. Margaret Thornfield, or any other
drafting-stage persona above. This mirrors, at the skill-authoring layer, the
same never-self-grade principle this document's Gate A/Gate B separation
enforces at the fleet build layer: a drafter is never its own reviewer.
