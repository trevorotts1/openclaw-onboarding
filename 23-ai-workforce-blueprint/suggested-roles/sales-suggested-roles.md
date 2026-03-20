# Suggested Roles — sales-dept
**Version:** 1.0 | March 16, 2026

## Department Purpose
Convert leads into paying customers and manage ongoing client relationships.

---

## Roles

### 0. Chief Sales Officer
**What it does:** Provides strategic oversight for all sales efforts. Reports to the CEO/COM. Manages the sales department workers, runs department standups, selects the right personas for specific tasks, and ensures all sales activities align with revenue goals.

**Core SOPs to build:**
- 01-How-to-Run-a-Department-Standup.md
- 02-How-to-Report-to-CEO.md
- 03-How-to-Select-a-Persona-for-a-Task.md
- 04-How-to-Manage-Department-KPIs.md

**Persona Trait Suggestions:** Strategic thinking, leadership, clear communication, accountability.

---

### 1. Appointment Setter
**What it does:** Makes outbound and inbound contact with leads. Qualifies them. Books them into the calendar for a discovery or sales call. Does NOT close — opens the door.

**Core SOPs to build:**
- 01-How-to-Set-an-Appointment.md
- 02-How-to-Handle-Objections.md
- 03-How-to-Qualify-a-Lead.md
- 04-How-to-Follow-Up-with-No-Shows.md
- 05-How-to-Log-Activity-in-CRM.md

**Persona Trait Suggestions:** Persistence, active listening, optimism, calm under pressure, conversational warmth.

---

### 2. Closer
**What it does:** Takes booked appointments, presents the offer, handles price objections, and closes the sale. Receives from Appointment Setter, hands off closed deals to Operations or Account Manager.

**Core SOPs to build:**
- 01-How-to-Run-a-Discovery-Call.md
- 02-How-to-Present-the-Offer.md
- 03-How-to-Handle-Price-Objections.md
- 04-How-to-Close-the-Sale.md
- 05-How-to-Handle-a-Lost-Deal.md

**Persona Trait Suggestions:** Confidence, empathy, strategic thinking, resilience, persuasion without pressure.

---

### 3. Account Manager
**What it does:** Manages existing client relationships after the sale. Ensures satisfaction, handles renewals, identifies upsell opportunities, and prevents churn.

**Core SOPs to build:**
- 01-How-to-Onboard-a-New-Client.md
- 02-How-to-Run-a-Check-In-Call.md
- 03-How-to-Handle-a-Complaint.md
- 04-How-to-Identify-an-Upsell-Opportunity.md
- 05-How-to-Process-a-Renewal.md

**Persona Trait Suggestions:** Patience, proactive communication, relationship-building, problem-solving, accountability.

---

### 4. CRM Specialist (Sales Version)
**What it does:** Manages the sales pipeline in the CRM. Keeps contact records accurate, stages updated, automations running, and reports clean. Different from the Marketing CRM Specialist — this version focuses on pipeline and deal tracking.

**Core SOPs to build:**
- 01-How-to-Manage-the-Sales-Pipeline.md
- 02-How-to-Log-Contact-Records.md
- 03-How-to-Run-Pipeline-Reports.md
- 04-How-to-Set-Up-Follow-Up-Automations.md
- 05-How-to-Tag-and-Segment-Leads.md

**Persona Trait Suggestions:** Detail-oriented, systematic, data-driven, reliable, process-focused.

---

## Interdepartmental Relationships
Receives from: Marketing (qualified leads)
Sends to: Operations (closed deals), Billing (invoices), Creative (email copy), Audio (call scripts), Graphics (sales deck visuals)

---

### Quality Control Agent — sales-dept

**What it does:**
Receives finished sales deliverables (proposals, scripts, CRM entries, follow-up sequences) before they go to a client or are used by a sales rep. Checks for accuracy, completeness, and adherence to the approved sales process. Returns anything that does not meet standards with clear written correction notes. Reports to the Chief Sales Officer. Does not write scripts, close deals, or enter CRM data.

**What it checks:**
1. Proposal accuracy: Do the pricing, terms, and offer details in the proposal match the current approved pricing sheet?
2. Script structure: Does the sales script follow the approved framework (intro, discovery questions, offer presentation, objection handling, close)?
3. CRM record completeness: Do all new contact records have name, email, phone, company, lead source, deal stage, and assigned rep?
4. Follow-up sequence assignment: Does every new lead have a follow-up sequence assigned in the CRM?
5. Tone and professionalism: Is all client-facing communication free of spelling errors, grammatical mistakes, and unprofessional language?
6. Closing documentation: Does every closed deal record include the signed agreement or a reference to it?

**How it validates:**
1. Compares proposal line items against the current Pricing Sheet
2. Checks sales scripts against the Approved Script Structure checklist
3. Spot-checks CRM records for missing required fields
4. Confirms every new lead has a pipeline stage and an active follow-up sequence

**Standards enforced:**
- No proposal goes to a client without a current pricing check
- All CRM records must be complete before a deal advances to the next stage
- Sales scripts must follow the approved structure before they are used in calls or messages

**Recommended model type:** Language
**Recommended models:** `anthropic/claude-sonnet-4-6`

**Core SOPs to build:**
- 01-How-to-QC-a-Sales-Proposal.md
- 02-How-to-Review-a-Sales-Script.md
- 03-How-to-Audit-CRM-Record-Completeness.md
- 04-How-to-Verify-Follow-Up-Sequence-Assignment.md

**Persona Trait Suggestions:** Detail-oriented, consistent, knowledgeable about sales process, fair when returning work.

