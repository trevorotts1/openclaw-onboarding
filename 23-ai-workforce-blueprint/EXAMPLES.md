# AI Workforce Blueprint - Good and Bad Examples

## Example: Good Department Structure

```
blackceo-workforce/
  sales-dept/
    lead-generation/
      00-START-HERE.md
      01-how-to-qualify-leads.md
      02-how-to-run-discovery-call.md
      03-how-to-follow-up.md
      good-examples.md
      bad-examples.md
      tools.md
    closing/
      00-START-HERE.md
      01-how-to-present-offer.md
      02-how-to-handle-objections.md
      good-examples.md
      tools.md
  marketing-dept/
    content-writer/
      00-START-HERE.md
      01-how-to-write-email-campaign.md
      02-how-to-write-social-post.md
      good-examples.md
      tools.md
  universal-sops/
    00-ROUTING.md
    tools.md
```

**Why this is good:**
- Every role has a 00-START-HERE.md so the AI always knows where to begin
- Tasks are numbered and separated (one file = one task)
- Good and bad examples give the AI a quality target
- Routing file at the top level so the AI never guesses which department owns a task

---

## Example: Bad Department Structure

```
my-stuff/
  sales/
    notes.md
    stuff-to-do.md
  marketing/
    random-ideas.txt
```

**Why this is bad:**
- No START-HERE file - AI doesn't know what this role does
- "notes.md" and "stuff-to-do.md" don't tell the AI HOW to do anything
- Mixed file types (.txt, .md) - use .md only
- No routing file - AI guesses which folder to go to
- No numbered tasks - AI can't follow a sequence

---

## Example: Good 00-START-HERE.md

```markdown
# Lead Generation - Start Here

## What This Role Does
Finds, qualifies, and routes new leads to the Closing team.

## Who Owns This Role
Sales Department > Lead Generation

## Top Tasks (read these files in order)
1. 01-how-to-qualify-leads.md - How to score and filter incoming leads
2. 02-how-to-run-discovery-call.md - Script and framework for discovery calls
3. 03-how-to-follow-up.md - Follow-up sequences and timing rules

## Tools This Role Uses
- Convert and Flow (GHL): CRM, pipeline management
- Calendly: booking discovery calls
- Google Workspace: email and documents

## Rules for This Role
- Never move a lead to Closing without a completed qualification score
- All discovery calls must be logged in GHL within 24 hours
- Follow-up sequence runs for 21 days maximum

## Where to Find Examples
- Good examples: good-examples.md
- Bad examples: bad-examples.md
```

**Why this is good:**
- Clear purpose statement
- Numbered task list with file references
- Tools list so AI knows what to use
- Explicit rules so AI doesn't improvise

---

## Example: Good 00-ROUTING.md (Universal SOPs)

```markdown
# Task Routing - Which Department Handles What

## Sales Tasks
- New lead came in → sales-dept/lead-generation/
- Proposal needed → sales-dept/closing/
- Contract to send → sales-dept/closing/

## Marketing Tasks
- Write email → marketing-dept/content-writer/
- Social media post → marketing-dept/content-writer/
- Ad copy → marketing-dept/content-writer/

## Finance Tasks
- Invoice a client → finance-dept/billing/
- Payment failed → finance-dept/billing/
- Expense report → finance-dept/billing/

## Operations Tasks
- Onboard new client → ops-dept/client-success/
- System is broken → ops-dept/tech-support/
- Schedule meeting → ops-dept/scheduling/

## When You Are Unsure
If the task does not match any category above:
1. Ask: "What is the end goal of this task?"
2. Route to the department whose purpose most closely matches that goal
3. If still unsure, default to ops-dept/ and let the Operations team route it further
```
