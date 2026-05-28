<!-- OPERATOR HEADER (5 lines) — DO NOT EDIT BELOW -->
<!-- Source: openclaw-cloudflare-tunnel-prompt (1).md v5.14 — lines 2403-2497 -->
<!-- Section: Step 9.9 — Install Compliance Keyword Detection -->
<!-- This file is a VERBATIM extraction from the v5.14 playbook. Do not summarize. -->
<!-- Patch source: skill-38-patch-1 agent — 2026-05-28 -->

## Step 9.9 — Install Compliance Keyword Detection

Hard-coded keyword triggers that override normal agent behavior for regulatory compliance.

**A. Write `$MASTER_FILES_DIR/compliance-keywords.md`:**

```markdown
# Compliance Keyword Detection

Regulatory triggers that override normal agent behavior. Checked at the
START of every reply turn (before classification, before sentiment).

## SMS opt-out (FCC required)

If customer's message contains ANY of (case-insensitive, whole word):
`STOP`, `UNSUBSCRIBE`, `END`, `QUIT`, `CANCEL`, `OPTOUT`, `OPT-OUT`

Then:
1. Do NOT reply.
2. Call GHL skill (or `POST /contacts/{contactId}/tags`) to add the
   `sms-opted-out` tag.
3. Remove contact from any active SMS campaigns in GHL.
4. Log: "SMS opt-out received from contact <id>; tagged and removed
   from campaigns."
5. If on a non-SMS channel and these keywords appear, treat as standard
   message — they're SMS-specific.

## Email unsubscribe

If customer's email body or subject contains: `unsubscribe`,
`remove me`, `take me off`, `stop emails`

Then:
1. Do NOT reply.
2. Add tag `email-opted-out` via GHL skill.
3. Log the opt-out.

## GDPR data deletion request

If message (any channel) contains: `delete my data`, `right to be
forgotten`, `GDPR deletion`, `delete my account`, `erase my information`

Then:
1. Send acknowledgment: "I've received your data deletion request. A
   team member will process it within 30 days per GDPR requirements
   and confirm when complete."
2. Tag contact as `gdpr-deletion-requested`.
3. Notify operator IMMEDIATELY (not subject to quiet hours).
4. Do NOT auto-delete — humans must verify identity and process.

## Healthcare compliance (HIPAA) — for healthcare clients

If client vertical is `healthcare` AND message contains symptom or
diagnosis keywords (configurable per client; defaults include:
"symptoms", "diagnosed", "prescription", "medication", "side effect",
"pain", "bleeding", specific condition names):

Then switch to compliance-mode reply:
"Thanks for reaching out. For your privacy and safety, medical
questions are best handled directly by your provider. I've notified
the office team to follow up with you securely."

Tag as `healthcare-compliance-mode`. Notify operator.

## Financial compliance (FINRA/SEC) — for financial clients

If client vertical is `financial` AND message contains investment
advice keywords ("should I buy", "is this stock", "investment advice",
"financial advice", specific ticker symbols):

Then switch to compliance-mode reply:
"Thanks for the question. Specific investment recommendations need to
come from your licensed advisor. I'll have the team reach out to you
to schedule a proper conversation."

Tag as `financial-compliance-mode`. Notify operator.

## Operator customization

Operator can add custom triggers for their vertical at the bottom of
this file under a `## Custom Triggers` section.
```

**B. Insert into AGENTS.md** as Step 0.7 (BEFORE classification in Step 1):

```markdown
### Step 0.7 — Compliance keyword check

Before any other processing, scan the customer's message against
compliance-keywords.md. If any compliance trigger fires, follow the
specified action (opt-out, GDPR, healthcare, financial) and exit.
Compliance overrides everything else.
```

**C. Append to Run Manifest:** "Step 9.9 complete — compliance-keywords.md created, AGENTS.md Step 0.7 inserted."
