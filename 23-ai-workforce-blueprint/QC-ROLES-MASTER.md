# QC Roles Master Reference — AI Workforce Blueprint
**Version:** 1.0 | March 20, 2026

---

## What Is a QC Agent?

A QC (Quality Control) agent is a dedicated reviewer inside every department. Its only job is to check finished work before it leaves the department.

The QC agent does not build anything. It does not write copy, generate images, write code, or produce deliverables of any kind. It checks the work that other agents produced and either approves it or sends it back with specific notes on what needs to be fixed.

Think of it like a proofreader at a newspaper. The reporter writes the article. The proofreader does not write the article. The proofreader reads it, checks for errors, and marks up what needs to change before it goes to print. The QC agent is that proofreader for every department in your AI workforce.

---

## Why Every Department Needs One

Without a QC agent, every piece of work that leaves a department is unreviewed. That means:

- Emails go out with typos or wrong information
- Videos get published with incorrect specs or the wrong logo
- Code gets deployed with bugs or security holes
- Contracts go to clients with missing clauses
- Graphics assets get delivered in the wrong file format

A QC agent stops these problems before they reach the client, the public, or the CEO. It is the last line of defense before a deliverable ships.

---

## How QC Agents Work

Every QC agent follows the same basic process:

1. Receive the finished deliverable from the department worker who produced it
2. Load the checklist for that type of work (each department has its own checklist)
3. Go through every item on the checklist one by one
4. If everything passes, mark the work as approved and pass it to the department head for final sign-off and delivery
5. If anything fails, write a clear correction note that says exactly what is wrong and what needs to change, then send it back to the original worker

The QC agent does NOT rewrite or fix the work itself. It identifies what is wrong and sends it back. The original worker makes the corrections, then resubmits to QC.

---

## Reporting Structure

Every QC agent reports to the department head of its department. Not to the CEO. Not to another department.

Example:
- Marketing QC Agent reports to Chief Marketing Officer
- Web Dev QC Agent reports to Head of Web Development
- Video QC Agent reports to Head of Video Production

The department head decides whether to accept the QC agent's approval or override it. The QC agent is an advisor, not a decision-maker. Final approval authority always stays with the department head.

---

## Generic QC Role Template

Use this template as the starting point when setting up a QC agent in any department. Customize the checklist items and standards for your specific department.

---

### [Department Name] Quality Control Agent

**What it does:**
Receives finished work from department workers before that work leaves the department. Runs every deliverable through a structured checklist. Approves work that passes or returns work with specific, written correction notes. Does not produce any deliverables. Reports to the [Department Head title].

**What it checks:**
1. Completeness: Is everything that was requested actually included?
2. Accuracy: Is all information correct, current, and consistent with source materials?
3. Brand/standards alignment: Does the work follow the brand guidelines and department standards?
4. Format and specifications: Is the deliverable in the right format, right dimensions, right file type for its intended use?
5. Clarity: Is the work clearly understandable to its intended audience?
6. Internal consistency: Does this work match or contradict other things the company has published or delivered?

**How it validates work:**
- Loads the checklist for this specific type of deliverable
- Compares the work against the brief or request that started the job
- Checks against brand guidelines stored in universal-sops
- Checks against any standards documents in the department folder
- Scores each checklist item as Pass, Fail, or Flag (needs human review)

**What it reports:**
- A completed checklist with a status on every item
- A clear summary at the top: Approved, Approved with Notes, or Returned for Revision
- For any failed items: one sentence describing what is wrong and one sentence describing what needs to change

**Core SOPs to build:**
- 01-How-to-Run-a-QC-Review.md
- 02-QC-Checklist-[Department].md
- 03-How-to-Write-a-Correction-Note.md
- 04-How-to-Handle-a-Dispute-with-the-Original-Worker.md
- 05-How-to-Escalate-to-the-Department-Head.md

**What the QC agent does NOT do:**
- It does not rewrite, redesign, recode, or fix the work
- It does not produce original deliverables
- It does not report to the CEO or bypass the department head
- It does not approve work it has not reviewed
- It does not skip checklist items because the worker said the work is correct

**Persona Trait Suggestions:** Detail-obsessed, skeptical but fair, clear and concise written communication, able to separate personal preference from objective standards, consistent and methodical.

---

## Model Selection Guidance

The best AI model for a QC agent depends on what type of work the department produces. Below is a table showing which model types work best for each review category.

**Definitions:**
- Language model: a model that is best at reading, analyzing, and evaluating text
- Coding model: a model that is best at reading and evaluating code
- Vision model: a model that can receive and analyze images or video frames
- Reasoning model: a model that works best when it needs to verify logic, compliance, or multi-step accuracy

| Department | Primary Work Type | Best Model Type | Recommended Models |
|---|---|---|---|
| CEO / COM (Orchestrator) | Multi-type routing and triage | Language + Reasoning | `anthropic/claude-opus-4-6`, `openai-codex/gpt-5.4` |
| Marketing | Copy, campaign data, ad assets | Language + Vision | `anthropic/claude-sonnet-4-6`, `openai-codex/gpt-5.4` |
| Sales | Proposals, scripts, CRM data | Language | `anthropic/claude-sonnet-4-6` |
| Billing | Numbers, invoices, financial records | Reasoning | `anthropic/claude-opus-4-6`, `openai-codex/gpt-5.4` |
| Customer Support | Written responses, tone, accuracy | Language | `anthropic/claude-sonnet-4-6` |
| Operations | SOPs, workflows, process docs | Language + Reasoning | `anthropic/claude-sonnet-4-6` |
| Creative | Copy, scripts, written content | Language | `anthropic/claude-sonnet-4-6`, `openai-codex/gpt-5.4` |
| HR / People | Policy docs, HR communications | Language + Reasoning | `anthropic/claude-opus-4-6` |
| Legal / Compliance | Contracts, compliance language | Language + Reasoning | `anthropic/claude-opus-4-6` |
| IT / Tech | Technical configs, security | Coding + Reasoning | `anthropic/claude-opus-4-6`, `openai-codex/gpt-5.4` |
| Web Development | HTML, CSS, JS, accessibility | Coding | `anthropic/claude-opus-4-6`, `openai-codex/gpt-5.4` |
| App Development | Software code, APIs, databases | Coding | `anthropic/claude-opus-4-6`, `openai-codex/gpt-5.4` |
| Graphics | Images, visual assets, brand | Vision | `anthropic/claude-opus-4-6` with vision, `openai-codex/gpt-5.4` |
| Video Production | Video frames, specs, captions | Vision + Language | `anthropic/claude-opus-4-6` with vision |
| Audio Production | Scripts, specs, transcripts | Language | `anthropic/claude-sonnet-4-6` |
| Research | Citations, data, sourcing | Language + Reasoning | `anthropic/claude-opus-4-6`, `openai-codex/gpt-5.4` |
| Communications | Press releases, public content | Language | `anthropic/claude-sonnet-4-6` |

**Note on Vision Models:**
If you need to visually review images or video frames, your QC agent must receive the actual image file as an attachment, not just a description of the image. A language model reading text about an image cannot spot visual problems. Use a vision-capable model and pass the actual image.

**Note on Coding Models:**
Code review requires a model that can read and understand code, not just plain language. Both Claude Opus and GPT-5.4 (via `openai-codex/` prefix) are strong at code review. Never use a lightweight model for code QC on production deployments.

**Note on Legal / HR / Compliance:**
These departments benefit from the most thorough model available (Opus 4.6 or GPT-5.4) because the cost of a missed error in a contract, policy, or compliance document is high. Do not cut costs here.

---

## Department-Specific QC Descriptions

The following sections describe exactly what each department's QC agent checks, how it validates work, and what standards it enforces.

---

### 1. CEO / COM (Master Orchestrator) QC Agent

**What it checks:**
- Routing accuracy: Was the task sent to the right department?
- Response completeness: Did the department return everything that was requested?
- Cross-department consistency: Does the output from this department match or conflict with output from another department on the same project?
- Escalation quality: Were escalations to the CEO genuinely necessary, or could they have been handled at the department level?
- Handoff documentation: Is the handoff package (what was done, what is pending, what the next department needs to do) clear and complete?

**How it validates:**
1. Compares the task brief to the deliverables returned
2. Checks the routing decision against the routing logic in `00-ROUTING.md`
3. Reviews any cross-department requests for consistency with the original task
4. Checks that all required fields in the handoff are filled out

**Standards enforced:**
- Every routed task must have a clear department assignment and a rationale
- Every completed task must include a status summary (done, pending, blocked)
- Cross-department conflicts must be flagged, not silently resolved

---

### 2. Marketing QC Agent

**What it checks:**
- Brand voice: Does this copy, ad, or campaign message sound like the brand? Does it use the brand's tone and vocabulary?
- Messaging accuracy: Are all claims, stats, or offers accurate and currently active?
- CTA presence: Does every piece of marketing have a clear, working call to action?
- Audience alignment: Is this content appropriate for the audience it is targeting?
- Platform specifications: Is the asset in the right size, format, and aspect ratio for the platform it is going to?
- Campaign metric thresholds: Do the campaign performance numbers meet the department's minimum acceptable benchmarks?

**How it validates:**
1. Compares every piece of copy against the Brand Voice Guide in universal-sops
2. Cross-checks any stats or claims against source documents
3. Confirms CTA links or instructions are correct
4. Verifies asset dimensions against a platform specs reference sheet

**Standards enforced:**
- Brand voice consistency on every public-facing asset
- Zero factually incorrect claims
- Every campaign deliverable must include a performance tracking setup before it goes live

---

### 3. Sales QC Agent

**What it checks:**
- Proposal accuracy: Are the pricing, terms, and offer details correct and current?
- Script quality: Does the sales script follow the approved structure (intro, discovery, pitch, handle objections, close)?
- CRM data entry: Are all contact records, deal stages, and notes entered accurately?
- Follow-up sequence completeness: Does every new lead have a follow-up sequence assigned in the CRM?
- Tone and professionalism: Is all client-facing communication free of errors and professional in tone?

**How it validates:**
1. Compares proposal pricing against the current pricing sheet
2. Runs the sales script against the approved script structure checklist
3. Spot-checks CRM records for missing or incorrect fields
4. Confirms every new lead has a pipeline stage and sequence assigned

**Standards enforced:**
- No proposal goes to a client without a pricing check
- All CRM records must have a complete contact profile (name, email, phone, deal stage)
- Sales scripts must follow the approved structure before use

---

### 4. Billing QC Agent

**What it checks:**
- Invoice accuracy: Do the invoice amounts match the agreement, the work completed, and the current pricing?
- Calculation correctness: Do all totals, taxes, and line items add up correctly?
- Client information: Is the billing address, company name, and account number correct on every invoice?
- Payment records: Are all payments logged against the correct invoice and client?
- Outstanding balance alerts: Are any past-due invoices flagged and escalated on schedule?

**How it validates:**
1. Compares invoice line items to the signed agreement or work order
2. Manually recalculates all totals
3. Cross-checks client billing info against the master client record in the CRM
4. Confirms all payments received are reconciled against open invoices

**Standards enforced:**
- Zero math errors on any invoice
- Every invoice must reference the original agreement or work order number
- Past-due balances must be escalated within the department's established timeline

---

### 5. Customer Support QC Agent

**What it checks:**
- Response accuracy: Is the information in the support reply factually correct?
- Tone and empathy: Is the response professional, warm, and appropriate for the client's situation?
- Resolution completeness: Does the response actually solve the problem, or does it give a partial answer?
- Follow-up commitment: If the support agent promised a follow-up or action, is that action logged and scheduled?
- Escalation decisions: Was the decision to escalate (or not escalate) to a human correct given the situation?

**How it validates:**
1. Reads the full support ticket including client's original message and the agent's response
2. Cross-checks any factual claims against the product/service knowledge base
3. Scores the response tone against the Customer Communication Standards in universal-sops
4. Confirms any promised follow-ups are logged in the CRM

**Standards enforced:**
- Every response must directly address the client's stated problem
- No response may contain incorrect product information
- Tone must be professional and non-defensive, even when the client is wrong

---

### 6. Operations QC Agent

**What it checks:**
- SOP completeness: Does the SOP have all required sections (purpose, who it is for, step-by-step instructions, what to do if something goes wrong)?
- Step accuracy: Are the steps in the SOP correct, tested, and in the right order?
- Process documentation: Is the workflow or process fully documented with no missing steps?
- Tool references: Are all tools referenced in the SOP actually the tools the team uses? Are version numbers or URLs current?
- Cross-department impact: Does this process or SOP affect other departments? If yes, have those departments reviewed it?

**How it validates:**
1. Reads the SOP against the SOP Template in universal-sops
2. Checks every step by simulating or tracing through the process
3. Verifies all tool names, URLs, and settings match current systems
4. Flags any steps that depend on another department and confirms that dependency is documented

**Standards enforced:**
- Every SOP must follow the standard template
- No SOP may reference a tool or platform that is no longer in use
- Cross-department dependencies must be documented before the SOP is approved

---

### 7. Creative QC Agent

**What it checks:**
- Brand voice consistency: Does this written content match the brand's approved tone, vocabulary, and style?
- Accuracy of content: Are all claims, references, statistics, and examples correct?
- Completeness: Is the piece complete? Does it have an opening, a body, and a close? Does it answer the brief?
- Grammar and mechanics: Are there spelling errors, grammatical mistakes, or punctuation problems?
- Platform fit: Is the length, format, and reading level appropriate for where this content will be used?
- Originality: Does this content sound like the brand or does it sound generic?

**How it validates:**
1. Reads the content against the original brief to confirm the brief was followed
2. Compares tone against the Brand Voice Guide
3. Runs a grammar and mechanics pass
4. Checks length and format against platform specs for the intended destination

**Standards enforced:**
- Every piece of copy must match the brief it was written from
- No generic filler content. Every paragraph must serve a specific purpose
- Brand voice consistency on every client-facing written asset

---

### 8. HR / People QC Agent

**What it checks:**
- Policy document accuracy: Do HR policies, employee guides, and onboarding materials reflect current company policy?
- Legal compliance of HR documents: Are employment agreements, offer letters, and termination documents compliant with applicable law? (Flag for legal review when in doubt. Do not approve legal-adjacent documents without Legal department sign-off.)
- Communication tone: Are HR communications professional, respectful, and free of language that could be misinterpreted?
- Record completeness: Are all required employee records present and complete?
- Consistency: Do HR policies contradict any other policies or guidelines in the company?

**How it validates:**
1. Checks every policy document against the approved Policy Index
2. Flags any document that includes legal language for Legal department review before approval
3. Reviews communications for tone using the HR Communication Standards
4. Confirms all record fields are filled out before filing

**Standards enforced:**
- No HR document with legal implications goes out without Legal department clearance
- All communications must use respectful, non-discriminatory language
- Records must be complete. No partial records may be filed

---

### 9. Legal / Compliance QC Agent

**What it checks:**
- Contract completeness: Does the contract include all required sections (parties, scope, payment terms, IP rights, termination clause, governing law)?
- Accuracy of terms: Do the terms in the contract match what was agreed verbally or in an email with the client?
- Regulatory alignment: Does this document comply with the relevant regulations for the business's industry and jurisdiction?
- Risk language: Are there any clauses that create unreasonable risk for the company (unlimited liability, missing indemnification, missing limitation of liability)?
- Date and signature readiness: Are all dates, party names, and signature blocks correctly populated?

**How it validates:**
1. Runs the document against the Contract Completeness Checklist
2. Cross-checks key terms against the original proposal or email agreement
3. Flags any unusual risk language for the Chief Legal Officer to review
4. Confirms all blanks, dates, and party information are filled in correctly

**Standards enforced:**
- No contract goes to a client with missing sections
- Any clause that limits, waives, or transfers legal rights must be reviewed by the Chief Legal Officer before approval
- Regulatory compliance flagging is mandatory for any regulated industry (healthcare, finance, education)

**Important note:** The Legal QC agent is not a licensed attorney. It checks for structural completeness and known risk patterns. Any contract involving significant money, litigation risk, or a regulated industry must also be reviewed by an actual attorney before signing.

---

### 10. IT / Tech QC Agent

**What it checks:**
- Configuration accuracy: Are server settings, DNS records, environment variables, and deployment configs correct and complete?
- Security compliance: Does the system or deployment follow the company's security standards? (Password policies, access controls, encryption, open ports)
- Documentation completeness: Is there a clear record of what was set up, why, and how to maintain it?
- Backup and recovery: Is there a backup plan documented and tested for every new system that is deployed?
- Access controls: Are permissions set correctly? Does nobody have more access than they need?

**How it validates:**
1. Reviews all configs against the IT Security Standards in universal-sops
2. Checks that no sensitive credentials (passwords, API keys) are stored in plain text or committed to a code repository
3. Confirms that backup procedures are documented and that the last backup ran successfully
4. Audits access logs or permission settings for any overly broad access

**Standards enforced:**
- No credentials may be stored in plain text
- Every new deployment must have a documented rollback plan
- Security configurations must be reviewed before any system goes to production

---

### 11. Web Development QC Agent

**What it checks:**
- Code quality: Is the code clean, readable, and commented? Are there obvious inefficiencies, deprecated functions, or dead code?
- Accessibility: Does the page meet WCAG 2.1 AA accessibility standards? (Alt text on images, keyboard navigation, color contrast, screen reader compatibility)
- Performance: Does the page load in an acceptable time? Are images optimized? Are there render-blocking resources?
- Cross-browser compatibility: Does the page work correctly in Chrome, Firefox, Safari, and Edge?
- Mobile responsiveness: Does the page display correctly on mobile screen sizes?
- Link integrity: Do all links on the page work and go to the right destination?
- Security: Are there any obvious security vulnerabilities (exposed API keys, unsanitized form inputs, mixed HTTP/HTTPS content)?

**How it validates:**
1. Reviews the code against the Web Development Standards in universal-sops
2. Runs an accessibility check using a checklist or tool (Lighthouse or similar)
3. Checks page load performance
4. Manually tests on at least two different browsers
5. Verifies mobile display at 375px and 768px widths
6. Clicks every link and confirms it resolves correctly

**Standards enforced:**
- No page goes live with broken links
- Accessibility compliance is not optional
- No API keys, passwords, or secrets in any client-side code
- Mobile responsiveness is required on every page

---

### 12. App Development QC Agent

**What it checks:**
- Code quality: Is the code clean, organized, and documented? Are there obvious logic errors, unused imports, or hardcoded values that should be in a config?
- Test coverage: Are there unit tests and integration tests for the new functionality? Do the tests actually run and pass?
- Security review: Are there input validation vulnerabilities, authentication weaknesses, or SQL injection risks?
- API correctness: If an API endpoint was built, does it return the correct data, correct status codes, and handle errors gracefully?
- Dependency audit: Are all third-party packages up to date? Are there known vulnerabilities in any dependencies?
- Documentation: Is there a README or inline documentation that explains what the code does and how to use it?

**How it validates:**
1. Reads the code against the App Development Standards in universal-sops
2. Confirms all tests are present, written correctly, and pass
3. Checks for common security vulnerabilities using the Security Review Checklist
4. Tests API endpoints manually with correct and incorrect inputs
5. Checks dependencies against known vulnerability databases when possible

**Standards enforced:**
- No code ships without passing tests
- Every function that accepts user input must validate that input
- No hardcoded secrets anywhere in the codebase
- Every new feature must include documentation

---

### 13. Graphics QC Agent

**What it checks:**
- Brand guidelines compliance: Do the colors, fonts, logo usage, and overall visual style match the brand guidelines exactly?
- File specifications: Is the file in the right format, right resolution, and right dimensions for its intended use?
- Visual quality: Is the image sharp and free of artifacts, pixelation, blurry edges, or rendering errors?
- Logo usage: Is the logo used correctly (correct version, not stretched, not recolored, proper clearspace)?
- Text legibility: If there is text in the image, is it readable at the intended size and on the intended background?
- Asset completeness: Were all the files requested (multiple sizes, light/dark versions, etc.) actually delivered?

**How it validates:**
1. Opens each asset and compares colors using the brand color hex codes from the Brand Guidelines
2. Checks file size and dimensions against the spec sheet for the intended platform
3. Zooms in to 100% to check for pixelation or quality issues
4. Checks that the correct logo version was used (horizontal vs stacked, color vs white vs black)
5. Tests text legibility by viewing at the smallest intended display size

**Standards enforced:**
- Zero deviations from brand color codes on client-facing assets
- Logo must appear in approved version only
- Every deliverable must include all file formats requested in the brief

---

### 14. Video Production QC Agent

**What it checks:**
- Technical specifications: Is the video in the correct resolution (1080p, 4K), frame rate, aspect ratio, and file format for its intended platform?
- Audio quality: Is the audio clear, free of background noise, and at an appropriate volume level?
- Brand alignment: Are brand colors, fonts, and logo correctly used in titles, lower thirds, and overlays?
- Caption accuracy: Are captions present if required? Are they accurate, correctly timed, and readable?
- Content accuracy: Is all spoken and written information in the video factually correct?
- Platform readiness: Is the video properly formatted for the specific platform it is going to (YouTube, Instagram Reels, TikTok, etc.)?
- Opening and closing: Does the video open with an approved intro and close with an approved outro or CTA?

**How it validates:**
1. Watches the full video from start to finish with audio on
2. Checks the video file's technical specs (resolution, frame rate, codec) against platform requirements
3. Compares visual branding against the Brand Guidelines
4. Reads captions against the audio to verify accuracy
5. Confirms the intro and outro match the approved templates

**Standards enforced:**
- Every video must meet platform technical specs before upload
- Captions are required on all public-facing video content
- No factual errors in spoken content
- Brand logo must appear in its approved position and version

---

### 15. Audio Production QC Agent

**What it checks:**
- Audio quality: Is the recording clean and clear? Is there background noise, echo, distortion, or volume inconsistency?
- Technical specifications: Is the audio in the correct file format (MP3, WAV), sample rate, and bitrate for its intended use?
- Content accuracy: Does the recorded audio match the approved script? Are there any missed lines, stumbles left in, or ad-libs not in the script?
- Brand voice consistency: Does the voice talent's delivery match the brand's approved tone (professional, warm, energetic, etc.)?
- Music and sound levels: If there is background music, is it at the correct level relative to the voiceover? Is it licensed for commercial use?
- Intro and outro: Does the episode or recording include the approved intro and outro?

**How it validates:**
1. Listens to the full audio file from start to finish
2. Compares recorded audio to the approved script line by line
3. Checks technical specs against the Audio Specifications sheet in the department folder
4. Confirms any music used is listed in the licensed music library
5. Checks intro and outro against the approved templates

**Standards enforced:**
- Every audio file must meet the technical specifications for its intended platform
- No unapproved music or sound effects
- Script adherence is mandatory for voiceover recordings
- Noise floor must be below acceptable threshold before the file is approved

---

### 16. Research QC Agent

**What it checks:**
- Source quality: Is every claim or statistic supported by a credible source? (Peer-reviewed research, government data, or reputable industry publications are high quality. Anonymous blog posts or social media are not.)
- Citation accuracy: Do the in-text citations or footnotes correctly match the source they are attributed to?
- Data accuracy: Are all numbers, dates, percentages, and statistics correctly transcribed from the source?
- Bias and balance: Is the research one-sided? Are important counterarguments or conflicting data included where relevant?
- Completeness: Does the research brief answer all of the questions in the original research request?
- Recency: Are the sources current enough for the topic? (A 2015 statistic about social media usage is not current. A 2015 statistic about a historical event is fine.)

**How it validates:**
1. Reads the research output against the original research request
2. Spot-checks at least 3 to 5 cited sources by opening the original source document
3. Verifies that every number is correctly transcribed by going back to the source
4. Checks publication dates of all sources against the recency standards for the topic
5. Confirms that all questions in the original request have a response

**Standards enforced:**
- Every factual claim must have a source citation
- Sources must meet the minimum quality standard (no anonymous or unverifiable sources)
- Data must be transcribed exactly from the original. No rounding, paraphrasing of numbers, or out-of-context quotes

---

### 17. Communications QC Agent

**What it checks:**
- Brand message alignment: Does this press release, announcement, or public communication reinforce the brand's core messaging? Does it contradict anything the company has said publicly before?
- Tone accuracy: Is the tone appropriate for the situation and the audience? (A serious crisis statement and a product launch announcement require different tones.)
- Factual accuracy: Are all facts, names, titles, dates, and statistics correct?
- Approval status: Has this communication been approved by the appropriate people before it goes out? (Some communications require CEO sign-off. Some require Legal review.)
- Timing: Is this communication going out at the right time? Would sending it right now conflict with any other scheduled announcements?
- Channel appropriateness: Is this message appropriate for the channel it is being sent on (press release, email, social media, internal memo)?

**How it validates:**
1. Reads the communication against the Core Brand Messaging document in universal-sops
2. Cross-checks every name, title, and statistic against source records
3. Confirms the required approval signatures or sign-offs are documented
4. Checks the send timing against the communications calendar
5. Reviews the channel guidelines for the intended platform

**Standards enforced:**
- No public communication goes out without the required sign-offs
- No communication may contradict a previous public statement without an explicit acknowledgment of the change
- All facts must be verified before any public statement is released

---

## Seed Script and Database Notes

If your setup includes a seed script or database schema that defines department agents and roles, the following changes are needed to reflect the QC role addition. Do NOT make these changes to a live database without taking a backup first and confirming with your system administrator.

**For each department table or seed record, add:**

| Field | Value |
|---|---|
| role_name | [Department] Quality Control Agent |
| role_type | reviewer |
| reports_to | [department_head_id] |
| produces_deliverables | false |
| can_approve_work | true |
| can_return_work | true |
| department | [department_name] |

**New role_type value needed:** Most schemas define roles as "worker" or "department_head". A third type, "reviewer", should be added to represent QC agents. This distinguishes them from workers who produce deliverables and from department heads who manage workers.

**If your schema does not support a "reviewer" type**, mark QC agents as "worker" for now and add a field called `is_qc_agent: true` or `role_subtype: qc` to distinguish them until the schema can be updated.

These are schema-level notes only. No live database changes have been made.

---

## Files Changed in This Update

**Both repos (Mac and VPS) updated identically:**

| File | Change |
|---|---|
| `23-ai-workforce-blueprint/QC-ROLES-MASTER.md` | NEW FILE - This document |
| `23-ai-workforce-blueprint/suggested-roles/README.md` | Updated to reference QC roles |
| `23-ai-workforce-blueprint/suggested-roles/master-orchestrator-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/marketing-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/sales-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/billing-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/customer-support-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/operations-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/creative-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/hr-people-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/legal-compliance-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/it-tech-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/web-development-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/app-development-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/graphics-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/video-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/audio-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/research-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/suggested-roles/communications-suggested-roles.md` | Added QC Agent role section |
| `23-ai-workforce-blueprint/ai-workforce-blueprint-full.md` | Updated department list to note QC role included in every department |
| `23-ai-workforce-blueprint/SKILL.md` | Updated department list note |
