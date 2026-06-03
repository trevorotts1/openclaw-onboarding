# SOP PA-01-07: Attachment & Document Filing

**Department:** Inbox Manager (01-inbox-manager)
**SOP Type:** DMAIC
**Version:** 1.0
**Last updated:** {{GENERATION_DATE}}
**Generated for:** {{COMPANY_NAME}}

---

## When to Run

Continuous — every time an email with an attachment arrives. Also: weekly audit of saved attachments.

**Frequency:** Real-time during inbox triage; weekly audit on Friday.

**Inputs:** Emails with attachments (PDFs, documents, images, spreadsheets, presentations, contracts, invoices), and any files {{OWNER_NAME}} asks to save.

---

## Define

- **Problem:** Attachments arrive in the inbox and stay there — buried in email threads, impossible to find later, and vulnerable to being lost when emails are archived or deleted. {{OWNER_NAME}} spends time searching for "that PDF someone sent last month" when it should be saved, named, and findable in 5 seconds. Research shows that knowledge workers spend 19% of their time searching for information (IDC). Systematic attachment filing eliminates this entirely for email-originated documents.
- **Goal:** Every business-relevant attachment is saved to {{DOCS_TOOL}} within the same processing sweep it arrives. Files are named with a consistent convention: "[YYYY-MM-DD] [Sender or Company] — [Document Description].[ext]" and placed in the correct folder based on: client, project, or document type. Any attachment can be located in under 10 seconds.
- **Scope:** All attachments to business emails. Includes: contracts, proposals, invoices, receipts, presentations, spreadsheets, images, and documents. Excludes: personal photos, memes, non-business files, and email signature images.

---

## Measure

- **CTQ 1 — Filing completeness:** Percentage of business-relevant attachments saved to {{DOCS_TOOL}} within the same processing sweep. Target: 100%.
- **CTQ 2 — Naming compliance:** Percentage of saved files following the naming convention. Target: 100%.
- **CTQ 3 — Retrievability:** Time to locate any saved attachment from the past 90 days when asked. Target: 10 seconds or less.
- **Metrics:** Attachments saved today (count), attachments missed (count — found during weekly audit), storage space used for email attachments (trending down = good).

---

## Analyze

1. **Attachment classification.** Attachments fall into predictable categories: (a) Client deliverables — proposals, reports, creative work (save by client folder), (b) Contracts and legal — agreements, NDAs, terms (save by legal/contracts folder with high-security access), (c) Financial — invoices, receipts, statements (save by finance folder, organized by month), (d) Internal documents — team resources, templates, reference materials (save by department or topic), (e) Media — images, videos, audio files (save by project or media type). Each category has a home folder. If a category does not have a home folder, create one.
2. **The email-as-filing-cabinet anti-pattern.** When people leave attachments in their inbox, they are using email as a document management system. This fails because: (a) email search is slow and imprecise, (b) attachments get lost when threads are deleted, (c) there is no version control — which version of the contract was the final one? (d) attachments in email are not shareable with the team. Every attachment saved to {{DOCS_TOOL}} is one step away from this anti-pattern.

---

## Improve

1. **The save-during-triage habit.** When you process an email with an attachment, save the file BEFORE you archive or file the email. The workflow is: open attachment, save to {{DOCS_TOOL}} with correct name, note the saved location, process the email (archive or flag for {{OWNER_NAME}}). This takes 20 seconds per attachment and prevents the "I will save it later" trap.
2. **The naming convention is non-negotiable.** Every file gets: date prefix (ISO format: YYYY-MM-DD), sender or company name, and descriptive title. "Proposal.pdf" is useless. "2026-06-02 Acme Corp — Q3 Marketing Proposal v3.pdf" is findable. If {{OWNER_NAME}} sends you a file to save with a vague name, rename it before saving. Never save a file called "Document1.pdf" or "Final_Final_v2.pdf."
3. **Version tracking.** When a revised document arrives, do not overwrite the original. Save the new version with an incremented version number: "...v1.pdf," "...v2.pdf." Add a note to the file description in {{DOCS_TOOL}}: "v2 received 2026-06-02 — includes updated pricing section." If {{OWNER_NAME}} asks "which version of the Acme contract is current?" you can answer in 5 seconds.
4. **Weekly attachment audit (Friday).** Review the week's saved attachments: any misspelled names? any files in the wrong folder? any attachments that should have been saved but were missed (cross-check against the week's processed emails)? Fix errors immediately.

---

## Control

- **Friday audit:** Cross-check the week's saved attachments against the processed email log. Any missed? File them now. Track missed-attachment rate weekly — target: zero.
- **Monthly folder review:** Review the {{DOCS_TOOL}} folder structure with {{OWNER_NAME}}. Is the organization still intuitive? Any folders that need to be split (too many files) or merged (too few files)?
- **Retrieval speed test:** Once per month, have someone (or {{OWNER_NAME}}) ask you to find 3 specific attachments from the past 90 days. Time yourself. Target: all 3 found in under 30 seconds total.

---

---

## CTQ Checks

- [ ] Every business-relevant attachment saved to {{DOCS_TOOL}} within the same processing sweep it arrives
- [ ] File naming follows the convention: "[YYYY-MM-DD] [Sender or Company] — [Document Description].[ext]" — zero files named "Document1.pdf" or "Final_Final_v2.pdf"
- [ ] Any attachment can be located in under 10 seconds when {{OWNER_NAME}} asks
- [ ] New versions are saved alongside originals with incremented version numbers — originals never overwritten
- [ ] Weekly Friday audit completed — cross-checked saved attachments against the processed email log

## Definition of Done

Every business attachment from processed emails is saved to {{DOCS_TOOL}} with a findable name, in the correct folder, and any attachment from the past 90 days can be retrieved in under 10 seconds.

## Escalation

- **Specialist 02 (Calendar & Scheduling Manager)** — if an attachment is a contract or agreement with a deadline that needs calendar tracking
- **Specialist 04 (Task & Priority Manager)** — if an attachment contains an action item or deliverable that needs task creation
- Escalate to {{OWNER_NAME}} — if a saved attachment appears to contain sensitive financial, legal, or personal data that may require access restrictions beyond standard filing

## Tone & Persona Note

Filing is invisible until it's not — and when {{OWNER_NAME}} needs that one contract from three months ago, your naming convention is the difference between "I can't find it" and "here it is." Treat every attachment like it will be urgently needed in 90 days. The extra 10 seconds you spend naming it correctly saves {{OWNER_NAME}} 10 minutes of frustrated searching. You are building the library that {{OWNER_NAME}} will rely on without ever having to think about it.

---

*See also: how-to.md Section 4 (Weekly Operations — Friday attachment audit step)*
