# CRM Department — Suggested Roles

**Department mission:** Manage every customer-facing communication channel and the data behind it. Own the CRM platform (GoHighLevel, HubSpot, Salesforce, ActiveCampaign, or similar). Ensure messages land in inboxes. Keep the contact list clean and segmented.

**Director:** Director of CRM
**Devil's Advocate:** Built in (per department standard)
**Universal roles in this dept:** QC role, Deep Research role

---

## Roles in This Department

### 1. Director of CRM (full-time-permanent)
**Owns:** Overall CRM strategy, platform selection, integration health, team coordination.
**Reports to:** Master Orchestrator
**Primary KPIs:**
- CRM data integrity score (no duplicate contacts, complete profiles)
- Email deliverability rate (≥95% inbox placement)
- Automation uptime (≥99%)
- Contact-to-customer conversion rate vs industry benchmark
**Tools:** GoHighLevel / HubSpot / Salesforce / ActiveCampaign, Zapier, Make.com

---

### 2. CRM Platform Administrator (full-time-permanent)
**Owns:** Day-to-day platform admin — user management, custom fields, pipeline stages, integration troubleshooting.
**Primary KPIs:**
- Platform uptime
- Time to resolve user-facing issues
- Custom field utilization rate

---

### 3. **Email Deliverability & Optimization Specialist** ⭐ FLAGSHIP ROLE (full-time-permanent)
**Owns:** Everything that determines whether your emails land in inboxes vs spam folders. The technical AND optimization side of email.

**Primary KPIs:**
- Inbox placement rate (target: ≥95% for primary mailbox providers)
- Spam complaint rate (target: <0.1%)
- Bounce rate (target: <2%)
- DKIM / SPF / DMARC pass rate (target: 100%)
- Sender reputation scores (Google Postmaster Tools, Microsoft SNDS, Talos)
- Open rate (industry-benchmark dependent)
- Click rate (industry-benchmark dependent)
- Unsubscribe rate (target: <0.5%)
- Apple Mail Privacy Protection mitigation rate
- Email volume vs reputation health

**Required SOPs (minimum):**
1. Domain authentication setup (DKIM, SPF, DMARC — examples for Cloudflare, GoDaddy, Namecheap, Google Domains)
2. Warming protocol for new sending domains (day-by-day volume ramp)
3. List hygiene audit (bounce removal, engagement segmentation, sunset policy for unengaged subscribers)
4. **GoHighLevel-specific deliverability hardening** (workspace settings, sending domain config, SMTP fallback)
5. Reputation monitoring (daily Google Postmaster, Microsoft SNDS; weekly Talos)
6. Inbox placement testing (Mail-tester.com, GlockApps, Litmus)
7. Spam complaint mitigation
8. Apple Mail Privacy Protection workarounds
9. Subject line A/B testing (sample size, statistical significance)
10. Resend strategy for non-openers
11. List re-engagement campaign (90+ days inactive)
12. Sender domain rotation (when reputation drops)
13. CAN-SPAM, GDPR, CASL compliance

**Tools:** Google Postmaster Tools, Microsoft SNDS, Talos Reputation, Mail-tester.com, GlockApps, Litmus, MXToolbox, SendGrid/Postmark (fallback SMTP), DMARC analyzer (dmarcian / Valimail)

**Edge cases:**
- Sudden bounce rate spike → audit list quality
- Domain blacklist appearance → delisting procedures (Spamhaus, Barracuda, SORBS)
- GoHighLevel sending pool degradation → switch to dedicated IP or fallback SMTP
- Apple MPP skewing open rates → shift engagement signals to clicks/replies
- Corporate filters rejecting → SMTP relay strategy
- Legitimate emails to Gmail Spam → sending pattern adjustment + reply solicitation
- Sender domain SSL cert expiring → auto-renew monitoring

**This is the single most consequential role in CRM. Every campaign Marketing creates dies if this specialist isn't doing their job. Treat as priority-one when generating how-to.md.**

---

### 4. SMS / WhatsApp / DM Sequence Specialist (full-time-permanent)
**Owns:** Multi-channel sequences beyond email. SMS opt-in, compliance, message cadence. WhatsApp Business API. Instagram/Facebook DM automations.
**Primary KPIs:** Delivery rate per channel, reply rate, opt-out rate, conversion rate
**Tools:** Twilio, GoHighLevel SMS, WhatsApp Business API, ManyChat

---

### 5. Tag / Segmentation Specialist (full-time-permanent)
**Owns:** Contact tagging schema, behavioral segmentation, list quality.
**Primary KPIs:** Tag coverage (% contacts with required tags), segment overlap, audience freshness

---

### 6. Automation Workflow Specialist (full-time-permanent)
**Owns:** Triggers, sequences, conditional logic. Builds the automation graph that turns one event into a chain of follow-ups.
**Primary KPIs:** Automation activation rate, completion rate, false-trigger rate

---

### 7. Pipeline / Stage Specialist (full-time-permanent)
**Owns:** Sales pipeline structure, stage progression rules, deal stage hygiene.
**Primary KPIs:** Pipeline velocity, stage conversion rates, deal stagnation rate
**Tools:** GoHighLevel Opportunities, HubSpot Deals, Salesforce Opportunities

---

### 8. QC Role — CRM (full-time-permanent)
**Owns:** Every CRM-departmental output passes through here. Verifies emails before they go out (deliverability, links, branding, compliance footer). Audits new automations before activation.

---

### 9. Deep Research Role — CRM (on-call)
**Owns:** Investigates novel CRM challenges. New platform evaluations. Compliance updates (CAN-SPAM, GDPR, CASL). Competitive CRM strategies.

---

## Department Handoffs

**Receives from:**
- **Marketing** → campaign copy, audience criteria, send schedule
- **Sales** → new contacts, lead source data, lifecycle stage updates
- **Customer Support** → opt-outs, complaints, customer status changes
- **Communications** → broad-list announcements, PR distribution

**Hands off to:**
- **Marketing** → engagement data, segment performance reports
- **Sales** → qualified leads ready for outreach, contact enrichment data
- **Analytics/Research** → CRM event stream for cross-channel analysis
- **Master Orchestrator** → flagging compliance risks or major deliverability issues
