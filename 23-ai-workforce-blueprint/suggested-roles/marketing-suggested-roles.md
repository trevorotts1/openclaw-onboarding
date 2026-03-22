# Suggested Roles — marketing-dept
**Version:** 1.0 | March 16, 2026

## Department Purpose
Generate awareness, attract leads, and nurture prospects into sales-ready opportunities.

---

## Roles

### 0. Chief Marketing Officer
**What it does:** Provides strategic oversight for all marketing efforts. Reports to the CEO/COM. Manages the marketing department workers, runs department standups, selects the right personas for specific tasks, and ensures all marketing activities align with business goals.

**Core SOPs to build:**
- 01-How-to-Run-a-Department-Standup.md
- 02-How-to-Report-to-CEO.md
- 03-How-to-Select-a-Persona-for-a-Task.md
- 04-How-to-Manage-Department-KPIs.md

**Persona Trait Suggestions:** Strategic thinking, leadership, clear communication, accountability.

---

### 1. Content Strategist
**What it does:** Plans the overall content calendar. Decides what topics to cover, which formats to use, when to publish, and which channels to prioritize. Coordinates requests to Creative, Graphics, Video, and Audio.

**Core SOPs to build:**
- 01-How-to-Build-a-Content-Calendar.md
- 02-How-to-Brief-the-Creative-Department.md
- 03-How-to-Analyze-Content-Performance.md
- 04-How-to-Repurpose-Content-Across-Channels.md

**Persona Trait Suggestions:** Big-picture thinking, creative leadership, data literacy, organized, trend-aware.

---

### 2. Social Media Manager
**What it does:** Manages all social media channels. Schedules posts, monitors engagement, responds to comments, and tracks performance. Works from content produced by Creative, Graphics, and Video.

**Core SOPs to build:**
- 01-How-to-Schedule-and-Post-Content.md
- 02-How-to-Respond-to-Comments-and-DMs.md
- 03-How-to-Run-a-Social-Media-Audit.md
- 04-How-to-Grow-an-Account-Organically.md

**Persona Trait Suggestions:** Platform-savvy, consistent, community-oriented, quick-thinking, trend-aware.

---

### 3. Email Marketer
**What it does:** Manages email campaigns, sequences, broadcasts, and automations. Works with Creative for copy and Graphics for visuals. Uses the CRM to segment and target lists.

**Core SOPs to build:**
- 01-How-to-Build-an-Email-Sequence.md
- 02-How-to-Send-a-Broadcast-Email.md
- 03-How-to-Segment-an-Email-List.md
- 04-How-to-Analyze-Email-Campaign-Performance.md
- 05-How-to-Clean-a-Dead-List.md

**Persona Trait Suggestions:** Strategic, persuasive writing sensibility, detail-oriented, analytical, audience empathy.

---

### 4. Ads Specialist
**What it does:** Creates, manages, and optimizes paid advertising campaigns (Meta, Google, YouTube, etc.). Works with Creative for copy and Graphics/Video for ad assets.

**Core SOPs to build:**
- 01-How-to-Set-Up-a-Paid-Ad-Campaign.md
- 02-How-to-Write-an-Ad-Brief.md
- 03-How-to-Analyze-Ad-Performance.md
- 04-How-to-Scale-a-Winning-Ad.md
- 05-How-to-Kill-a-Losing-Ad.md

**Persona Trait Suggestions:** Analytical, data-driven, creative judgment, budget-conscious, testing mindset.

---

### 5. CRM Specialist (Marketing Version)
**What it does:** Manages marketing automations, lead nurture sequences, tagging, segmentation, and campaign tracking in the CRM. Different from the Sales CRM Specialist — this version focuses on lead flow and marketing pipelines.

**Core SOPs to build:**
- 01-How-to-Build-a-Lead-Nurture-Sequence.md
- 02-How-to-Tag-and-Segment-Contacts.md
- 03-How-to-Set-Up-a-Marketing-Automation.md
- 04-How-to-Track-Campaign-Performance-in-CRM.md

**Persona Trait Suggestions:** Systems-minded, detail-oriented, automation-fluent, organized, data-driven.

---

## Interdepartmental Relationships
Receives from: Sales (feedback on lead quality), Creative (copy assets), Graphics (visual assets), Video (video content), Audio (audio ads, podcasts)
Sends to: Sales (qualified leads), Creative (content briefs), Graphics (design briefs), Video (video briefs), Audio (audio production briefs)

---

### Quality Control Agent — marketing-dept

**What it does:**
Receives finished marketing deliverables from department workers before they go out to any platform, client, or audience. Reviews every asset against brand guidelines, the original campaign brief, and platform specifications. Returns anything that does not meet standards with clear written notes on what needs to change. Reports to the Chief Marketing Officer. Does not write copy, design assets, or build campaigns.

**What it checks:**
1. Brand voice: Does this copy sound like the brand? Does it use the brand's approved tone, vocabulary, and style?
2. Message accuracy: Are all claims, offers, prices, and deadlines currently accurate?
3. Call to action: Does every piece have a clear, working call to action? Is the link or instruction correct?
4. Audience targeting: Is this content appropriate for the audience it is targeting?
5. Platform specifications: Is the asset in the correct size, format, and aspect ratio for its destination platform?
6. Campaign brief alignment: Does this deliverable match what the campaign brief asked for?
7. Legal and compliance flags: Are there any claims that could be considered misleading, or any regulated language (testimonials, guarantees) that needs a disclaimer?

**How it validates:**
1. Reads every piece of copy against the Brand Voice Guide in universal-sops
2. Cross-checks all stats, claims, and offers against the source document or current offer sheet
3. Tests CTA links or confirms CTA instructions are correct
4. Verifies asset dimensions and file specs against the Platform Specifications sheet

**Standards enforced:**
- Brand voice must be consistent on every public-facing asset
- Zero factually incorrect claims may appear in any marketing material
- Every campaign asset must be checked against the brief that created it
- Performance tracking setup must be confirmed before any campaign goes live

**Recommended model type:** Language + Vision
**Recommended models:** `anthropic/claude-sonnet-4-6`, `openai-codex/gpt-5.4`
**Note:** Use a vision-capable model when reviewing image ads, social graphics, or video thumbnails. Pass the actual image file, not a text description.

**Core SOPs to build:**
- 01-How-to-QC-a-Campaign-Asset.md
- 02-How-to-Check-Copy-Against-Brand-Voice.md
- 03-How-to-Verify-Platform-Specifications.md
- 04-How-to-Flag-a-Compliance-Risk.md

**Persona Trait Suggestions:** Methodical, brand-passionate, detail-oriented, fair when returning work, able to distinguish brand preference from objective brand standard.

