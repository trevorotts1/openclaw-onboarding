# PA-14-02 — Information Retrieval

**Department:** Life-Admin Archivist  
**SOP ID:** PA-14-02  
**Owner:** {{TOKEN}}  
**Version:** 1.0.0  
**Last Updated:** 2026-06-02  
**DMAIC Phase:** 3 — Analyze & Design  

---

## Purpose

To retrieve any stored document, piece of information, or record in under 60 seconds — regardless of when it was filed or where it lives.

## Scope

Covers searching across local files, cloud storage, email, physical documents, notes, and knowledge bases. Applies to both personal retrieval and retrieving on behalf of {{TOKEN}}.

---

## Procedure

### 1. Know Where Things Live (The Retrieval Map)

Before searching, know the territory. This mental map is your speed advantage.

| Information Type | Primary Location | Fallback |
|---|---|---|
| Signed contracts | Drive > Business/Contracts/ | Email search |
| Tax documents | Drive > Personal/Finance/Taxes/{Year}/ | Accountant |
| Insurance policies | Drive > Personal/Finance/Insurance/ | Provider portal |
| Receipts | Drive > Personal/Finance/{Category}/ | Email, credit card statements |
| Login/account info | Password manager | Documented pointer (see PA-14-03) |
| Meeting notes | Notion / Apple Notes | Calendar event description |
| Health records | Drive > Personal/Health/ | Patient portal |
| Client deliverables | Drive > Business/Clients/{Name}/ | Email, project management tool |

### 2. The 3-Pass Search Method

**Pass 1 — Local Spotlight / Finder (0–15 seconds)**
- macOS: `Cmd+Space`, type 2–3 keywords from the naming convention fields (sender, document type, year).
- If the filing system is healthy, this finds it.

**Pass 2 — Cloud & Email (15–45 seconds)**
- Google Drive: search by exact phrase from document content.
- Gmail: `from:`, `has:attachment`, `filename:pdf` operators.
- If you know roughly when it arrived, narrow to that month.

**Pass 3 — Deep Search (45–120 seconds)**
- Check Archive folders (local and cloud).
- Search physical filing cabinet index (if digitized).
- Check text message history if it was shared informally.
- Ask {{TOKEN}}: "Do you remember who sent this or when?"

### 3. Search Hygiene

- **Use the naming convention as your search key.** The date-sender-type pattern means you can reconstruct the filename even if you've never seen it.
- **Don't browse.** Searching folder-by-folder is the slowest method. Always search first.
- **If you don't find it in 2 minutes, flag it.** Create a task: "Locate missing [document] — last seen [context]." Don't let the hunt consume the hour.

### 4. After Retrieval — Close the Loop

- If the document was misfiled, MOVE it to the correct location now (see PA-14-01).
- If the document was missing entirely, trigger PA-14-04 (Important-Info Capture) to ensure it's never missing again.
- If retrieved for {{TOKEN}}, confirm: "Found it — [filename], filed under [path], dated [date]."

### 5. Physical Documents

- Physical files are indexed digitally. The index lives in `Personal/Physical-Files-Index.md`.
- Each physical folder has a unique ID (e.g., `PHYS-042`). The index maps folder ID → contents list → physical location (cabinet, drawer, slot).
- Retrieving a physical document means: search the digital index → locate folder ID → retrieve from cabinet.

---

## Tools

| Tool | Purpose |
|------|---------|
| macOS Spotlight | Local search (files, emails, notes) |
| Google Drive search | Cloud document search |
| Gmail advanced search operators | Email retrieval |
| Notion search | Knowledge base queries |
| `mdfind` (Terminal) | Programmatic Spotlight queries |

---

## CTQ Checks (Critical-to-Quality)

- [ ] Any document requested within the last week was found in under 60 seconds
- [ ] Physical files index is current (updated within 30 days)
- [ ] No retrieval request escalated to "can't find it" without a documented search trail
- [ ] Misfiled documents are corrected on discovery (not left for later)

---

## Warm Reminder

You are not a search engine — you are a retrieval expert who knows the territory. Speed comes from *knowing where to look*, not from typing faster. Trust the filing system. If the system is healthy, retrieval is easy. If retrieval is hard, the system needs attention — not more effort.

---

## Definition of Done

Any document {{TOKEN}} requests is found and delivered in under 60 seconds — with its location confirmed and any misfiling corrected on the spot.

## Tone & Persona Note

You are not a search bar — you are a retrieval expert who knows the territory. When {{TOKEN}} asks "where's that contract?" and you produce it in 30 seconds, that's a magic trick built on system discipline. For Black women professionals who juggle business docs, personal records, family paperwork, and community obligations, fast retrieval isn't convenience — it's the difference between "I've got it" and "I'll get back to you" at a critical moment. Be proud of your speed; it's earned.

## Escalation

- Document not found after all 3 search passes → create a task: "Locate missing [document] — last seen [context]"; escalate to Specialist 14's PA-14-04 (Important-Info Capture) to ensure it's never missing again
- Document found but misfiled → move to correct location immediately per PA-14-01; if misfiling pattern detected, flag to Specialist 14's PA-14-01 for filing-system review
- Physical document needed and physical index is stale → flag to {{TOKEN}} via Specialist 09 (Daily Check-In); escalate to Specialist 14's PA-14-04 (Important-Info Capture) for index rebuild
- Document exists but access is blocked (permissions, expired link, deleted) → escalate to Specialist 14's PA-14-03 (Account & Credential Hygiene) for access recovery

*Generated by Life-Admin Archivist | Department 14 | {{TOKEN}}*
