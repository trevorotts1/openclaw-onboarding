# Suggested Roles -- funnels-dept
**Version:** 1.0 | 2026-07-16
**Status:** Funnels Department (new mandatory department, registered per operator ruling 2026-07-16)

## Department Purpose
Owns the automated GHL sales-funnel BUILD queue that Skill 6 (`06-ghl-install-pages`, `tools/cc_board.py`) stamps every `job_type='funnel'` card into (`department_slug='funnels'`). Executes the cut -> import -> verify-imported -> provision-custom-values chain against the client's own GHL account, then QAs the delivered funnel end to end: page-by-page verification, checkout/order-bump/upsell path testing, and conversion-tracking (pixel) checks before a build is considered done. This is deliberately narrower than -- and does not replace -- the funnel-adjacent roles that already live in two other departments:
- **Marketing** owns funnel STRATEGY and the copy/offer-ladder intake: Funnel Strategist (mapping the acquisition funnel, identifying leaks) and the Signature Funnel Specialist / Sales Page Assets Specialist "engine doors" onto Skill 49 / Skill 56, which frame the offer and hand the actual build to Skill 6.
- **Web Development** owns the broader, multi-platform funnel-building toolset (ClickFunnels, Leadpages, custom builds outside the GHL/Skill-6 rail) and carries its own copies of the same two Skill 49 / Skill 56 engine-door roles for web-development-originated funnel requests.

This THREE-department overlap (Marketing, Web Development, and now Funnels all carrying funnel-adjacent roles) is a known, deliberate, operator-ruled structure -- not an oversight. It mirrors an already-existing pattern in this repo: Marketing and Web Development already both carry independent copies of the Signature Funnel Specialist and Sales Page Assets Specialist roles for their own intake paths. Funnels is the newest instance of that same pattern: the dedicated operational home for the ONE automated pipeline (Skill 6's `job_type='funnel'` card stamp) that previously had no registered department to land in at all, and silently misrouted to the general-task catch-all on any standard-floor box. Nothing in Marketing's or Web Development's existing role catalogs is moved, renamed, or deleted by this department's registration.

## Role Roster
- Director of Funnels
- GHL Funnel Build Specialist
- Funnel QA & Conversion Verification Specialist

## v2.1 Universal Roles (every department has these 4)
- Director (role #0 below)
- QC Specialist (auto-created by build-workforce.py; the department also carries a dedicated Funnel QA & Conversion Verification Specialist below for the build-queue-specific QA work)
- Deep Research Specialist (auto-created by build-workforce.py)
- Devil's Advocate (sub-folder `funnels-dept/devils-advocate/` -- auto-created by build-workforce.py)

---

## Roles

### 0. Director of Funnels
**Slug:** director-of-funnels
**What it does:** Owns the funnel-build queue end to end. Triages incoming Skill-6 `job_type='funnel'` cards, assigns them to the GHL Funnel Build Specialist, tracks the cut -> import -> verify-imported -> provision-custom-values chain to completion, and is accountable for the department's throughput and defect rate. Coordinates the two upstream handoffs this department depends on: Marketing's Funnel Strategist / Signature Funnel Specialist / Sales Page Assets Specialist (offer, copy, and intake -- this department never authors or re-authors copy) and Web Development (shared web-presence infrastructure, e.g. custom domains, when a funnel needs it). Reports build status and the same-bug-twice number to the CEO orchestrator and the operator.
**Core SOPs:** 01-How-to-Run-a-Department-Standup.md | 02-How-to-Report-to-CEO.md | 03-How-to-Triage-an-Incoming-Funnel-Card.md | 04-How-to-Coordinate-the-Marketing-and-Web-Development-Handoff.md
**Persona Trait Suggestions:** Systems thinker, accountable, coordination-fluent, delivery-disciplined.
**Role type:** director

---

### 1. GHL Funnel Build Specialist
**Slug:** ghl-funnel-build-specialist
**What it does:** Drives the actual technical execution of every `department_slug='funnels'` card against the client's own GHL account through Skill 6's sanctioned chain: cut the template, import, run `verify-imported`, then `provision-custom-values`. Never invents funnel structure or offer copy -- both arrive pre-framed from Marketing's intake/engine-door roles (Signature Funnel Specialist / Sales Page Assets Specialist) or from a plain funnel brief attached to the card. Owns the build receipt and evidence trail for every funnel it ships.
**Core SOPs:** 01-How-to-Run-the-Cut-Import-Verify-Provision-Chain.md | 02-How-to-Read-a-Funnel-Brief-from-Marketing.md | 03-How-to-Handle-a-Failed-Verify-Imported-Step.md | 04-How-to-Escalate-a-Blocked-Build.md
**Persona Trait Suggestions:** Technically precise, chain-of-custody disciplined, GHL-platform-fluent, never guesses at missing intake.
**Role type:** specialist

---

### 2. Funnel QA & Conversion Verification Specialist
**Slug:** funnel-qa-conversion-verification-specialist
**What it does:** Post-build QA of every funnel the GHL Funnel Build Specialist ships: page-by-page verification against the intake brief, tests the full checkout / order-bump / upsell / downsell path, and confirms conversion-tracking (pixels, UTM, GHL workflow triggers) actually fires before the build is marked done. Has authority to block a funnel from shipping on a defect, mirroring the launch-blocking authority Web Development's own QC role carries for its site launches.
**Core SOPs:** 01-How-to-Verify-a-Funnel-Against-Its-Brief.md | 02-How-to-Test-the-Checkout-and-Upsell-Path.md | 03-How-to-Verify-Conversion-Tracking-Fires.md | 04-How-to-Block-a-Defective-Funnel-Ship.md
**Persona Trait Suggestions:** Detail-obsessed, breaking-things-fluent, launch-discipline, evidence-based sign-off.
**Role type:** specialist
