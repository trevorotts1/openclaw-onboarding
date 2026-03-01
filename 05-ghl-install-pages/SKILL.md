---
name: ghl-install-pages
description: >
  How to deploy HTML pages into GHL (Go High Level) or Convert and Flow using
  browser automation. This skill teaches the AI agent how to use Playwright to
  log in, navigate the page builder, paste code, save, preview, and publish
  funnel pages - all without the human needing to touch the builder themselves.
metadata:
  author: Trevor Otts, BlackCEO
  version: "1.0"
  priority: HIGH
---

# GHL / Convert and Flow - Install Pages

This skill is about deploying finished HTML code into the GHL (Go High Level)
or Convert and Flow page builder using browser automation. The AI agent drives
the browser, pastes the code, and handles all the clicks and navigation.

This is NOT about writing or designing the HTML. The HTML is already done
(usually from a SuperDesign export). This skill is purely about getting that
code into GHL so the page goes live.

## When to Use This Skill

- The user asks you to deploy, install, or publish a page in GHL
- The user asks you to put HTML into a Convert and Flow funnel or website
- The user asks you to update an existing GHL page with new code
- The user says "install this page" or "deploy this to GHL"
- You have finished HTML from SuperDesign and need to put it somewhere live

## Prerequisites

- Teach Yourself Protocol (TSP) must be learned first (skill 01)
- Backup Protocol must be learned first (skill 02)
- GHL Setup must be complete (skill 04) - the account must already exist
- Playwright must be installed for browser automation
- GHL login credentials must be stored in ~/clawd/secrets/.env

## What This Skill Covers

1. **Browser setup** - Viewport size (minimum 1440x900), persistent sessions
   so the user only logs in once, and anti-detection settings
2. **Login and session management** - How to log in, handle expired sessions,
   and deal with two-factor authentication (2FA) by pausing for the human
3. **GHL's iframe architecture** - The page builder loads inside nested
   iframes. You cannot just click elements on the main page. The skill
   explains how to find and switch into the correct iframe context.
4. **Selector strategy** - GHL changes their UI frequently. Every button and
   link has a chain of fallback selectors so automation does not break when
   GHL updates a label or class name.
5. **10-phase deployment process** - Navigate to Funnels, create a new funnel,
   add steps, open the builder, dismiss the AI popup, add a blank section with
   a code element, set full width, paste the HTML, save, and preview.
6. **Iframe deployment method** - For complex pages where GHL's own CSS
   conflicts with your code, host the HTML externally and embed it via iframe.
7. **Multi-page funnels** - How to loop through multiple pages (landing, sales,
   checkout, thank you) in a single funnel deployment.
8. **Updating existing pages** - How to find an existing funnel, open the page
   in the builder, replace the code, and save without creating duplicates.
9. **Error recovery** - Retry logic, screenshot capture on failure, and a
   recovery protocol for when things go seriously wrong.
10. **Publishing** - NEVER publish without explicit user approval. Always send
    a deployment report with screenshots first.

## Files in This Folder (Reading Order)

1. **SKILL.md** - You are here. Start with this file.
2. **ghl-install-pages-full.md** - The complete reference with all Playwright
   code, selector chains, helper functions, and step-by-step instructions.
   Read this when you are actually about to deploy pages.
3. **INSTRUCTIONS.md** - Additional operational instructions.
4. **INSTALL.md** - Installation steps if any tools are missing.
5. **EXAMPLES.md** - Example deployments and common scenarios.
6. **CORE_UPDATES.md** - What to add to AGENTS.md, TOOLS.md, and MEMORY.md.

## Critical Things to Know

- Always use `launchPersistentContext()` in Playwright, never `launch()`.
  Persistent context saves the login session so the user does not have to
  log in every single time.
- Always verify you are in the correct GHL sub-account before building.
  Deploying in the wrong sub-account means the client will not see the pages.
- Default to Funnels, not Websites, unless the user specifically says Website.
- The GHL code editor has no size limit. Paste the entire HTML in one block.
- GHL's builder needs time between actions. Wait for elements to load. Do not
  click too fast or the builder will not keep up.
- Every deployment ends with a report: what was built, preview screenshots at
  desktop/tablet/mobile sizes, and whether publishing is approved.
- Credentials go in ~/clawd/secrets/.env as GHL_EMAIL and GHL_PASSWORD.
  Never hardcode credentials in scripts.
