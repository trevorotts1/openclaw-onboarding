# SuperDesign - Usage Instructions

This document covers how to use SuperDesign day to day. It assumes you have already completed the installation steps in INSTALL.md. If you have not installed SuperDesign yet, go do that first.


## Understanding the Three Modes

SuperDesign can be used in three different ways. You do not need to use all three. Pick the one (or two) that fits how you work.

**Web App Mode** - You go to app.superdesign.dev in your browser, type what you want in the chat panel, and see designs appear on the canvas. Best for visual exploration and website cloning.

**CLI Mode** - You type commands in your terminal. Best for batch operations, automation, and when an AI agent is doing the work for you.

**IDE Extension Mode** - You use it inside your code editor (VS Code, Cursor, Windsurf). Best for unlimited generation using your own API key and working within a development workflow.


## The Core Workflow (Same for All Modes)

No matter which mode you use, the basic workflow follows these steps:

1. Decide what you want to build (landing page, about page, sales page, etc.)
2. Gather your brand info (colors, fonts, tone, audience)
3. Create a design using SuperDesign
4. Generate variations to explore different directions
5. Pick the best one and refine it
6. Export the code (HTML or React) and the style.md file
7. Add your real content (your words, your images, your links)
8. Deploy to your hosting platform


## How to Create a Design from Scratch

### Using the Web App

1. Go to https://app.superdesign.dev and log in.
2. Make sure you are in Design Mode (not Wireframe Mode). Design Mode gives you polished, production-ready output.
3. Click the chatbox at the bottom of the screen.
4. Type a detailed description of what you want. The more specific you are, the better the result. Include:
   - What type of page (landing page, about page, services page, etc.)
   - Your brand colors (hex codes if you have them, or descriptions like "deep purple and gold")
   - What sections you want and in what order
   - The overall feel you want (premium, warm, minimal, bold, etc.)
   - Who the page is for (your target audience)
5. Press Enter and wait. Generation takes 15 to 90 seconds depending on complexity.
6. Do NOT type anything else while the design is generating. Wait for the canvas to update.
7. Once the design appears, review it. Check that all the sections you asked for are present.

### Using the CLI

1. Open your terminal.
2. Create a new project:

   superdesign create-project --title "Your Page Name" --set-project-prompt "Describe what you want here" --json

3. Save the draftId from the response. You need this number for all future commands on this design.

### Using a Design System File (Recommended)

Instead of writing your design description inline, you can save it as a file and reference it. This is better for complex projects.

1. Create a file called design-system.md in your project's .superdesign/ folder.
2. In that file, write out your complete design rules: colors (with hex codes), fonts, spacing preferences, tone, audience, and any other brand guidelines.
3. Create your project using that file:

   superdesign create-project --title "Your Page Name" --set-project-prompt-file .superdesign/design-system.md --json


## How to Clone an Existing Website

Cloning lets you take any live website and bring it into SuperDesign as an editable starting point. This is incredibly useful when you see a design you love and want something similar.

### Cloning a Full Page

1. Open Google Chrome and navigate to the website you want to clone.
2. Scroll all the way down through the page to make sure all sections have loaded (some sites load content as you scroll).
3. Scroll back to the top.
4. Click the SuperDesign extension icon in your Chrome toolbar (top right area).
5. The extension overlay will appear on the page. Click "Clone page."
6. Wait for the import to complete (5 to 30 seconds depending on page complexity).
7. You will be redirected to app.superdesign.dev with the cloned design on your canvas.
8. The cloned design is now editable. Use the chatbox to make changes.

### Cloning a Single Component

Sometimes you only want one piece of a page, like a navigation bar or a pricing table.

1. Open Chrome and go to the website.
2. Click the SuperDesign extension icon.
3. Instead of clicking "Clone page," hover your mouse over the specific section you want. SuperDesign will highlight different sections as you hover.
4. Click on the specific element you want to capture.
5. That single component opens in SuperDesign as an editable piece.

You can clone components from multiple different websites and combine them into one page.

### What Gets Captured When You Clone

Things that transfer well:
- Layout structure (how elements are arranged)
- Color palette (the hex codes used throughout)
- Typography (font choices, sizes, weights)
- Spacing patterns (margins, padding)
- Component styles (buttons, cards, forms, navigation)

Things that do NOT transfer perfectly:
- Exact images (you get placeholders, not the original copyrighted images)
- Complex JavaScript animations (they may simplify)
- Backend functionality (forms, logins, databases)
- Pixel-perfect replication (it gets very close but it is a smart reconstruction)


## How to Generate Design Variations

Getting multiple versions of a design is one of SuperDesign's strongest features. There are three main methods.

### Method 1: Branching (Controlled Exploration)

Branching creates a separate copy of your design that you can experiment with. Your original stays untouched.

In the Web App: Use the chatbox to type something like "Create a branch with a darker, more luxurious color scheme."

In the CLI:

   superdesign iterate-design-draft --draft-id YOUR_DRAFT_ID -p "Dark theme with neon accents" -p "Soft pastels with rounded corners" -p "Bold minimalist with large typography" --mode branch --json

Each -p flag creates a separate variation. Three flags means three different versions.

### Method 2: Parallel Generation (Speed)

In the Web App, click the + icon at the top-right of the chat panel. This opens a new conversation that runs at the same time as your existing one. Give each conversation different instructions and they all generate simultaneously.

### Method 3: Prompt-Based Variations

Simply ask for multiple options in your prompt: "Give me three different layout options for this pricing section."

### How Many Variations to Generate

Default to 3 unless you have a specific reason for more. More than 5 becomes hard to evaluate.


## How to Refine a Design

After you have a design you like (or the best of several variations), use the chatbox or CLI to make targeted improvements.

In the Web App: Type one instruction at a time in the chatbox. Wait for each change to finish before submitting the next one.

Good refinement prompts:
- "Add more breathing room between sections"
- "Make the CTA button larger and more prominent"
- "Change the testimonial section background to a subtle gradient"
- "Make the hero section taller with more whitespace"

In the CLI (replace mode updates the design in place):

   superdesign iterate-design-draft --draft-id YOUR_DRAFT_ID -p "Add more whitespace between sections" --mode replace --json


## How to Export Your Design

When you are happy with a design, you need to export two things:

### Export 1: The Code (HTML or React)

This is the actual website code that can be pasted into a hosting platform or given to a developer.

- In the Web App: Click on the frame you want, then look for the Export or "View Code" option. Choose HTML format (recommended for broadest compatibility) or React format (for developer environments).
- In the CLI: superdesign get-design --draft-id YOUR_DRAFT_ID --output ./my-design.html

### Export 2: The style.md (Design System Document)

This is a text document that captures every design decision: exact hex colors, font names and sizes, spacing rules, button styles, and component patterns.

The style.md is extremely valuable because you can hand it to ANY AI tool and say "build me pages following these design rules" and the AI will know exactly what your site should look like. This means you can design one page in SuperDesign, export the style.md, and then have OpenClaw or Claude build your remaining pages using those same rules.

Always export both the code and the style.md. Save both to your local filesystem.


## How to Use Exports with Different Platforms

### Go High Level (GHL) / Convert and Flow

GHL does not support React. You must export as HTML with inline CSS.

Add this to your SuperDesign prompt: "Export as a single self-contained HTML file with all CSS inline or in a style tag. No external stylesheets. No React. No JavaScript dependencies."

To paste into GHL:
1. Open your funnel or website in GHL.
2. Add a section with a Code Element (under "Custom" in the elements panel).
3. Click "Open Code Editor" and paste your entire HTML code.
4. Make sure the section is set to "Allow rows to take entire width."
5. Save and preview.

### WordPress

Use a "Custom HTML" block in Gutenberg, or an "HTML" widget in Elementor. Include all CSS in a style tag. Use unique class names prefixed with "sd-" to avoid conflicts with your theme.

### Shopify

SuperDesign has a direct Shopify theme export option in the web app. Use this when available.

### Vercel / Netlify

Export as React code. These platforms support React and Next.js natively.

### Wix / Squarespace

These platforms have limited custom code support. It is often better to use SuperDesign as visual reference and build natively in their editors. Export the style.md and use it as a design guide.


## Post-Design Assembly (The Critical Step)

SuperDesign gives you the visual design and code. But the design will have placeholder text and placeholder images. Before you deliver anything, you MUST:

1. Replace all placeholder headlines with your real headlines.
2. Replace all placeholder body text with your real copy.
3. Replace all placeholder button text with your real calls to action.
4. Replace all placeholder images with your real images (or clearly mark them for the user to replace).
5. Update any meta tags (page title, description).
6. Verify the page looks correct on desktop (1200px wide), tablet (768px), and mobile (375px).
7. Read through ALL visible text and confirm no "Lorem ipsum" or "Your headline here" remains.
8. Check that all colors match your brand specifications.

Never deliver a design export with placeholder text as a finished product.


## The Smart Hybrid Workflow (Save Credits)

The Web App has limited free credits per week. Here is how to get maximum value:

1. Use the Web App only for cloning (this is the one thing only the Web App can do).
2. Export the style.md immediately after cloning.
3. Switch to the CLI or IDE Extension for all remaining work (variations, iterations, additional pages).
4. The CLI and IDE Extension use your own API key, so generation is unlimited.
5. Use the extract-brand-guide CLI command instead of cloning every reference site.

This way you use only 1-2 Web App credits instead of 20+.


## Key CLI Commands Quick Reference

Research and Inspiration:
   superdesign search-prompts --keyword "wellness landing page" --json
   superdesign extract-brand-guide --url https://example.com --json

Create:
   superdesign create-project --title "My Page" --set-project-prompt "description" --json
   superdesign create-project --title "My Page" --set-project-prompt-file ./design-system.md --json

Iterate:
   superdesign iterate-design-draft --draft-id ID -p "instruction" --mode replace --json
   superdesign iterate-design-draft --draft-id ID -p "Option A" -p "Option B" --mode branch --json

View:
   superdesign list --json
   superdesign gallery
   superdesign get-design --draft-id ID --json

Multi-Page Funnels:
   superdesign execute-flow-pages --draft-id ID --pages '[{"title":"Page 1","prompt":"description"}]' --json


## Design Best Practices

When prompting SuperDesign, keep these principles in mind for professional results:

1. Visual Hierarchy - The most important element (usually the headline) should be the largest and most prominent. CTAs should be impossible to miss.

2. Whitespace - Always include "generous whitespace" in your prompts. Space makes designs feel premium. Cramped designs feel cheap.

3. Typography - Use a maximum of two font families per design. One for headlines, one for body text. Body text should be at least 16px.

4. Color - Stick to 3-4 colors maximum plus neutrals. Use the 60/30/10 rule: primary color 60%, secondary 30%, accent 10%.

5. Consistency - All buttons should look the same. All headings should look the same. Spacing between sections should be uniform.

6. Mobile First - Always include "fully responsive, mobile-first" in your prompts. Over 60% of web traffic is mobile.

7. Section Flow for Landing Pages - Follow this order: Hero, Social Proof, Benefits, How It Works, Testimonials, Pricing, FAQ, Final CTA, Footer.


## Where to Find Design Inspiration

Before designing, browse these sites for ideas:

- Awwwards (awwwards.com) - Award-winning websites, the gold standard
- Dribbble (dribbble.com) - Quick visual inspiration, UI elements, trending styles
- SiteInspire (siteinspire.com) - Curated live websites, filterable by style and industry
- One Page Love (onepagelove.com) - Single-page website designs
- Lapa Ninja (lapa.ninja) - Massive library of landing page designs

When you find a site you love, you can clone it using the Chrome Extension and modify it to match your brand.


## Files and Folder Structure

All SuperDesign output lives locally on your computer in the .superdesign/ folder:

   .superdesign/
   - design-system.md (your design rules)
   - replica_html_template/ (HTML templates used as starting points)
   - design_iterations/ (all generated design files)
   - prompts/ (history of all prompts used)


## What to Do Next

For real examples showing SuperDesign in action, see the EXAMPLES.md file.
For the complete unabridged reference with every detail, see the superdesign-full.md file.
