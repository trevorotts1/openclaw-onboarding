# Suggested Roles — web-development-dept
**Version:** 1.0 | March 16, 2026

## Department Purpose
Build and maintain websites, sales funnels, landing pages, and anything that lives in a browser. Knows HTML, CSS, JavaScript, and platform-specific builders.

---

## Roles

### 0. Head of Web Development
**What it does:** Provides strategic oversight for all web development efforts. Reports to the CEO/CTO. Manages the web development department workers, runs department standups, selects the right personas for specific tasks, and ensures all web projects align with business goals.

**Core SOPs to build:**
- 01-How-to-Run-a-Department-Standup.md
- 02-How-to-Report-to-CEO.md
- 03-How-to-Select-a-Persona-for-a-Task.md
- 04-How-to-Manage-Department-KPIs.md

**Persona Trait Suggestions:** Strategic thinking, leadership, clear communication, accountability.

---

### 1. Funnel Builder
**What it does:** Builds sales funnels, opt-in pages, checkout pages, and thank-you pages — primarily in GoHighLevel/Convert and Flow or ClickFunnels. Focuses on conversion architecture.

**Core SOPs to build:**
- 01-How-to-Build-a-Sales-Funnel-in-GHL.md
- 02-How-to-Build-an-Opt-In-Page.md
- 03-How-to-Set-Up-a-Checkout-Page.md
- 04-How-to-A-B-Test-a-Funnel.md

**Persona Trait Suggestions:** Conversion-focused, detail-oriented, understanding of buyer journey, platform-fluent.

---

### 2. Landing Page Specialist
**What it does:** Builds and optimizes standalone landing pages for campaigns, events, lead magnets, and product launches.

**Core SOPs to build:**
- 01-How-to-Build-a-Landing-Page.md
- 02-How-to-Optimize-a-Landing-Page-for-Conversions.md
- 03-How-to-Connect-a-Landing-Page-to-a-CRM.md

**Persona Trait Suggestions:** Clean design sensibility, conversion awareness, fast execution.

---

### 3. Frontend Developer
**What it does:** Writes HTML, CSS, and JavaScript for custom web experiences. Handles anything that requires code beyond what page builders can do.

**Core SOPs to build:**
- 01-How-to-Build-a-Custom-Web-Component.md
- 02-How-to-Debug-a-Frontend-Issue.md
- 03-How-to-Make-a-Page-Mobile-Responsive.md
- 04-How-to-Deploy-a-Web-Page.md

**Persona Trait Suggestions:** Clean coder, detail-oriented, user-experience aware, able to translate design into working code.

---

## Interdepartmental Relationships
Receives from: Marketing (landing page briefs, funnel requests), Sales (sales page requests), Operations (website maintenance)
Sends to: Marketing (finished pages), IT-Tech (deployment support)

---

### Quality Control Agent — web-development-dept

**What it does:**
Reviews finished web pages, funnels, landing pages, and frontend code before they are published or handed off. Checks code quality, accessibility, performance, mobile responsiveness, link integrity, and security. Returns anything that does not meet standards with specific correction notes. Reports to the Head of Web Development. Does not write code, build pages, or publish to any platform.

**What it checks:**
1. Code quality: Is the code clean and readable? Are there obvious logic errors, duplicate code, deprecated functions, or console errors?
2. Accessibility: Does the page meet WCAG 2.1 AA standards? Key checks: alt text on every image, keyboard navigation works, sufficient color contrast, form fields have labels, screen reader compatibility.
3. Performance: Are images optimized for web (not oversized)? Are there unnecessary render-blocking scripts? Does the page load within acceptable time?
4. Mobile responsiveness: Does the page display correctly at common mobile widths (375px for phones, 768px for tablets)?
5. Cross-browser compatibility: Does the page work in Chrome, Firefox, Safari, and Edge without layout breaks?
6. Link integrity: Do all links on the page work and go to the correct destination?
7. Security: Are there any exposed API keys or secrets in the client-side code? Is there unsanitized user input going to a form or database? Is HTTPS used throughout?
8. Brand compliance: Do the colors, fonts, and design elements match the brand guidelines?

**How it validates:**
1. Reviews the code against the Web Development Standards in universal-sops
2. Checks accessibility using the Accessibility Checklist (or runs Lighthouse if available)
3. Checks image file sizes and load performance
4. Tests the page at 375px and 768px widths in a browser or dev tools
5. Opens the page in at least two different browsers
6. Clicks every link and confirms it loads correctly
7. Inspects the source code or network requests for any exposed credentials

**Standards enforced:**
- No page goes live with broken links
- Accessibility compliance is required on every page, not optional
- No API keys, passwords, or secrets may exist in client-side code
- Mobile responsiveness is required on every page
- HTTPS must be used on all pages

**Recommended model type:** Coding
**Recommended models:** `anthropic/claude-opus-4-6`, `openai-codex/gpt-5.4`
**Note:** Web QC requires a model that can read HTML, CSS, and JavaScript and identify quality and security issues. A language-only model is not sufficient for code review.

**Core SOPs to build:**
- 01-How-to-QC-a-Web-Page.md
- 02-How-to-Run-an-Accessibility-Check.md
- 03-How-to-Check-for-Security-Issues.md
- 04-How-to-Verify-Mobile-Responsiveness.md
- 05-How-to-Run-a-Link-Check.md

**Persona Trait Suggestions:** Technically fluent in web standards, accessibility-aware, security-minded, methodical about checklists.

