# Persona Matching Protocol
## How Personas Are Assigned to Agents and Sub-Agents

**Version:** 1.0.0
**Date:** March 27, 2026

---

## Core Principle

**Personas are NOT assigned to departments. Personas are attached to an agent or sub-agent at the task level.**

A persona is chosen fresh for every task based on three alignment layers. The same role in the same department may use different personas depending on what they are trying to accomplish.

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
No persona matching happens. The agent operates without persona guidance. This is a valid state. When Skill 22 is installed later, persona matching activates automatically.

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
