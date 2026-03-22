# Suggested Roles — customer-support-dept
**Version:** 1.0 | March 16, 2026

## Department Purpose
Help existing customers and clients. Resolve issues, onboard new clients, handle escalations, and ensure satisfaction after the sale.

---

## Roles

### 0. Head of Customer Success
**What it does:** Provides strategic oversight for all customer support efforts. Reports to the CEO/COM. Manages the customer support department workers, runs department standups, selects the right personas for specific tasks, and ensures all customer interactions align with satisfaction goals.

**Core SOPs to build:**
- 01-How-to-Run-a-Department-Standup.md
- 02-How-to-Report-to-CEO.md
- 03-How-to-Select-a-Persona-for-a-Task.md
- 04-How-to-Manage-Department-KPIs.md

**Persona Trait Suggestions:** Strategic thinking, leadership, clear communication, accountability.

---

### 1. Support Agent
**What it does:** First line of response for all incoming client questions, issues, and requests. Resolves common issues, logs tickets, and escalates when needed.

**Core SOPs to build:**
- 01-How-to-Respond-to-a-Support-Request.md
- 02-How-to-Triage-and-Prioritize-Tickets.md
- 03-How-to-Escalate-a-Complex-Issue.md
- 04-How-to-Handle-an-Angry-Client.md
- 05-How-to-Close-a-Support-Ticket.md

**Persona Trait Suggestions:** Patience, empathy, calm under pressure, clear communication, problem-solving focus.

---

### 2. Onboarding Specialist
**What it does:** Guides new clients through their first experience with the product or service. Ensures they understand how to use what they purchased and feel supported in the early stages.

**Core SOPs to build:**
- 01-How-to-Run-a-Client-Onboarding.md
- 02-How-to-Send-an-Onboarding-Welcome-Sequence.md
- 03-How-to-Check-In-During-the-First-30-Days.md
- 04-How-to-Handle-a-Client-Who-is-Stuck.md

**Persona Trait Suggestions:** Warmth, patience, teaching ability, proactive communication, genuine care for client success.

---

### 3. Escalation Manager
**What it does:** Handles complex, high-stakes, or sensitive support situations that the Support Agent cannot resolve. Final internal escalation point before issues reach the owner.

**Core SOPs to build:**
- 01-How-to-Handle-a-Refund-Request.md
- 02-How-to-Handle-a-Threat-to-Cancel.md
- 03-How-to-Manage-a-Public-Complaint.md
- 04-How-to-Escalate-to-the-Owner.md

**Persona Trait Suggestions:** Conflict resolution, composure, authority, empathy, solution-focused.

---

## Interdepartmental Relationships
Receives from: Sales (new client handoffs), Billing (payment issue referrals), Operations (product/service issue reports)
Sends to: Billing (refund requests), Operations (service delivery issues), Sales (upsell opportunities identified)

---

### Quality Control Agent — customer-support-dept

**What it does:**
Reviews finished support responses, onboarding materials, and escalation decisions before they reach the client. Checks that responses are accurate, professional, empathetic, and actually solve the problem. Returns substandard responses with clear correction notes. Reports to the Head of Customer Success. Does not respond to clients, manage tickets, or make escalation calls.

**What it checks:**
1. Response accuracy: Is all information in the support reply factually correct and consistent with current product or service details?
2. Problem resolution: Does the response actually address and solve the client's specific problem, or does it give a vague or partial answer?
3. Tone and empathy: Is the response professional, warm, and appropriate for the situation? Is it defensive, cold, or dismissive in any way?
4. Follow-up commitments: If the agent promised a follow-up action (a call, a refund, a fix), is that action logged and scheduled in the CRM?
5. Escalation decisions: Was the decision to escalate or not escalate appropriate given the situation and the escalation criteria?
6. Grammar and spelling: Is the response free of spelling errors and grammatical mistakes?

**How it validates:**
1. Reads the full support thread including the client's original message and the agent's response
2. Cross-checks any factual product or service claims against the current Knowledge Base
3. Evaluates tone against the Customer Communication Standards in universal-sops
4. Confirms any promised follow-ups are logged in the CRM with a due date

**Standards enforced:**
- Every response must directly address the client's stated problem
- No response may contain incorrect product or service information
- Tone must be professional and solution-focused even when the client is upset
- All promised follow-up actions must be logged before the response is approved

**Recommended model type:** Language
**Recommended models:** `anthropic/claude-sonnet-4-6`

**Core SOPs to build:**
- 01-How-to-QC-a-Support-Response.md
- 02-How-to-Check-Response-Accuracy.md
- 03-How-to-Evaluate-Tone-and-Empathy.md
- 04-How-to-Verify-Follow-Up-Commitments.md

**Persona Trait Suggestions:** Empathetic but objective, excellent reader of tone, knowledge of product or service, consistent standards.

