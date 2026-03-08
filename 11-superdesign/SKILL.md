---
name: superdesign
description: >
  Setup for SuperDesign - an AI-powered website design tool that creates visual
  designs and exports real code. Use before building any website or UI so the
  result looks professional instead of generic.
metadata:
  author: Trevor Otts, BlackCEO
  version: "1.0"
  priority: HIGH
---

# SuperDesign Setup

SuperDesign (superdesign.dev) is an AI design tool that creates website layouts,
exports real code (HTML or React), and generates a style guide document you can
hand to any AI tool to build matching pages. Think of it as your AI architect -
it draws up the blueprints and gives you the building materials.

This is a large, detailed skill. The full document covers everything from basic
setup to advanced funnel building and hosting platform compatibility. Read this
SKILL.md first to understand the scope, then go to the full document when you
need the details.

## When to Use This Skill

- The user asks to build, design, or redesign a website
- Someone says "design this page," "copy this website," or "create a landing page"
- Any UI or frontend work where you want professional results (not generic AI look)
- The user wants to clone an existing website and customize it
- Building a sales funnel, landing page, booking page, or membership page
- Setting up SuperDesign for the first time (CLI install, account login)

## What This Skill Covers

The full document is very comprehensive. Here are the major sections:

1. **What SuperDesign Is (and Is Not)** - It designs and exports code. It does NOT
   write your final copy, source your images, or host your website. You still need
   to add real content after exporting.

2. **Three Ways to Use It** - Web App (browser at app.superdesign.dev), CLI
   (terminal commands), and IDE Extension (inside VS Code, Cursor, or Windsurf).

3. **Quick Start Setup** - Installing the CLI, logging in, creating your first project.

4. **Chrome Extension for Cloning** - How to capture any live website and bring it
   into SuperDesign as an editable starting point. Step-by-step instructions.

5. **Design Variations** - Branching (separate copies to experiment with), parallel
   generation (multiple designs at once), and prompt-based variations.

6. **Exports Explained** - Three export types: React code, HTML/CSS, and style.md
   (a written design rulebook). The style.md is the most universally useful because
   any AI tool can read it and build matching pages.

7. **OpenClaw Integration** - How to take SuperDesign exports and use them with
   OpenClaw to build, modify, and deploy finished websites.

8. **Post-Design Assembly** - The critical step most people skip. After exporting,
   you must replace placeholder text with real copy, add real images, and verify
   the page works on desktop, tablet, and mobile.

9. **Hosting Platform Compatibility** - Detailed rules for GoHighLevel/Convert & Flow,
   WordPress, Shopify, Vercel, Netlify, Wix, Squarespace, and Kajabi. Each platform
   has different code requirements.

10. **GHL Deployment Walkthrough** - Click-by-click instructions for deploying
    SuperDesign code into GoHighLevel, including browser automation steps.

11. **10 Ready-to-Use Prompt Templates** - Lead capture, sales page, booking page,
    checkout, thank you, webinar registration, membership, about page, services,
    and waitlist pages.

12. **Design Best Practices** - Visual hierarchy, whitespace, typography, color,
    consistency, mobile-first thinking, alignment, and contrast rules.

13. **Smart Hybrid Workflow** - How to save SuperDesign credits by cloning once
    in the web app, then doing all remaining work locally with the CLI or IDE.

## Files in This Folder

Read them in this order:

1. **SKILL.md** - You are here. Overview and trigger conditions.
2. **superdesign-full.md** - The complete guide (very long - 2300+ lines). Contains
   everything: human guide, AI agent instructions, CLI commands, browser automation
   steps, prompt templates, hosting rules, and checklists. This is the file you
   execute from.
3. **INSTRUCTIONS.md** - Additional setup instructions if needed.
4. **INSTALL.md** - Installation-specific notes.
5. **EXAMPLES.md** - Example usage patterns.
6. **CORE_UPDATES.md** - What to add to your core .md files.
7. **superdesign.skill** - Skill definition file.

## Prerequisites

- The Teach Yourself Protocol (TYP) must be installed first.
- The Backup Protocol should be in place.
- Node.js version 16 or higher (for CLI installation).
- OpenClaw with skill install capability.

## Key Things the AI Agent Needs to Know

- **Design first, build second.** Always use SuperDesign to create the visual design
  before writing any website code. This prevents generic-looking AI websites.

- **Never deliver placeholder content.** SuperDesign exports have fake text and
  placeholder images. You MUST replace these with real copy and real images before
  showing anything to the user.

- **The style.md export is your secret weapon.** Design one page in SuperDesign,
  export the style.md, then use it to build all your other pages with any AI tool.
  This keeps every page visually consistent without designing each one individually.

- **Hosting platform matters.** Always ask where the page will be hosted BEFORE
  exporting. GoHighLevel needs self-contained HTML with inline CSS and no React.
  Vercel and Netlify can handle React. Getting this wrong means broken pages.

- **GHL-specific rules:** All CSS must be inline or in a style tag. Scripts must be
  separate from div tags. No external stylesheets. No React components.

- **Credit management:** The web app has limited free credits per week. The IDE
  extension uses your own API key (pennies per design, unlimited). Smart approach:
  clone once in the web app, do everything else locally.

- **CLI key commands:**
  - superdesign create-project - Start a new design project
  - superdesign iterate-design-draft - Refine or branch a design
  - superdesign extract-brand-guide - Capture a website's design DNA
  - superdesign gallery - Open visual gallery to compare designs
  - superdesign search-prompts - Find design inspiration

- **The full document follows TYP rules:** Save the deep file to the master files
  folder, only add short summaries to core .md files.

## How to Execute This Skill

1. Read superdesign-full.md completely before doing anything.
2. Follow the TYP file storage rules.
3. Install the CLI: npm install -g @superdesign/cli@latest
4. Install the skill: npx clawhub install superdesign
5. Log in: superdesign login
6. Verify: superdesign --help
7. Add the lightweight summaries to AGENTS.md, TOOLS.md, MEMORY.md, and IDENTITY.md
   as specified in the full document. Do not dump the full content into these files.
