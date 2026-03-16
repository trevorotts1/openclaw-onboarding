# Persona Re-Evaluation Protocol
**Version:** 1.0 | March 16, 2026

## Purpose
This protocol defines when and how to re-run the 4-Layer Persona Alignment check for any role. Persona selection is not a one-time decision — it should be revisited when the business, the role, or the owner's direction changes.

---

## The 4-Layer Alignment Check (Quick Reference)

Every persona assigned to a role must pass all 4 layers:

**Layer 1 — Company Alignment**
Does this persona reflect the company's mission, brand identity, and purpose?

**Layer 2 — Owner/CEO Alignment**
Does this persona align with the owner's personality, leadership style, and how they want the company represented?

**Layer 3 — Role/Functional Alignment**
Is this persona suited for what this role does day to day? Does it match the KPIs, job function, and department goals?
*Layer 3 = what they DO*

**Layer 4 — Beliefs and Principles Alignment**
Does this persona share the company's and owner's beliefs, principles, and values? Does it align with the deeper mission of the role and department?
*Layer 4 = WHY they do it and what they stand for*

A persona can pass Layer 3 and fail Layer 4. **Both must pass.**

---

## When to Trigger a Re-Evaluation

Re-run the 4-layer check when any of the following occur:

1. **Company goals change** — new mission, pivot, rebrand, or major strategic shift
2. **New department added** — personas for new roles need initial evaluation
3. **Owner's priorities shift** — the leader's vision or values have evolved
4. **Role responsibilities change significantly** — the job is fundamentally different now
5. **Persona is underperforming** — the AI in this role consistently produces output that feels off-brand, misaligned, or wrong in tone
6. **Quarterly review** — as part of the 90-day knowledge architecture review, check all active personas

---

## Re-Evaluation Process

### Step 1: Identify what changed
Write one sentence describing what changed and why re-evaluation is needed.

### Step 2: Pull the current persona assignment
Check `company-discovery/persona-alignment-notes.md` for the current persona mapped to this role.

### Step 3: Run all 4 layers against the current state
Score each layer: Pass / Fail / Partial

### Step 4: Determine outcome
- All 4 Pass → Keep current persona, document the re-evaluation date
- Any layer Fails → Identify which layer failed and why
- Run new persona search: which persona now scores highest on the failed layer(s)?

### Step 5: If replacing the persona
- Document the old persona, the reason for replacement, and the new selection
- Update `company-discovery/persona-alignment-notes.md`
- Notify the department that their role persona has been updated

---

## Documentation

All persona assignments and re-evaluations are tracked in:
`my AI company departments/company-discovery/persona-alignment-notes.md`

Format for each entry:
```
## [Role Name] — [Department]
Current Persona: [Persona Name]
Last Evaluated: [Date]
Layer 1 (Company): Pass/Fail — [notes]
Layer 2 (Owner): Pass/Fail — [notes]
Layer 3 (Functional): Pass/Fail — [notes]
Layer 4 (Beliefs): Pass/Fail — [notes]
Next Review: [Date or trigger]
```
