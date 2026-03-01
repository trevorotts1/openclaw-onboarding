# GHL Install Pages - How to Deploy Pages Day to Day

This document explains the step-by-step process for deploying HTML pages into GoHighLevel (Convert and Flow) using browser automation. If you have not completed the setup prerequisites, go read INSTALL.md first.

This assumes your HTML code is already written and ready to paste. This guide is about the process of getting that code into GHL's page builder.


## The 10-Phase Deployment Process

Deploying a page into GHL follows 10 phases in exact order. Do not skip phases. Do not change the order.


### Phase 1: Navigate to Funnels

1. Click "Sites" in the left sidebar of the GHL dashboard
2. Wait for the Sites section to load
3. Click the "Funnels" tab at the top of the page (use "Websites" tab only if the user specifically asked for a website, not a funnel)
4. Wait for the funnel list to load completely before proceeding

Important: 90% of the time you want "Funnels." Only use "Websites" if the user specifically requested a standalone website.


### Phase 2: Create a New Funnel

1. Click the "+ New Funnel" button (usually in the top-right area of the page)
2. A popup will appear with options. You will see choices like: Blank Funnel, AI, From Templates
3. Click "Blank Funnel" - always choose Blank because you have your own code
4. A name field will appear. Type a descriptive funnel name that matches the project (for example, "Soft Life Sanctuary Landing Page")
5. Click "Create"
6. Wait for the funnel workspace screen to load. This may take 3-5 seconds.
7. CRITICAL: Copy and save the URL from your browser's address bar. You will need this URL later when deploying multiple pages. This is called the "funnel workspace URL."


### Phase 3: Add Funnel Steps

Repeat this block for EACH page in the funnel (for example: Landing Page, Sales Page, Checkout, Thank You).

1. Click "Add New Step" on the workspace screen
2. A form will appear. Fill in the Step Name (for example, "Landing Page")
3. Fill in the Step Path - this is the URL-friendly path, using lowercase letters and hyphens (for example, "/landing" or "/sales-page" or "/checkout" or "/thank-you")
4. The path must be unique within this funnel - no two pages can have the same path
5. Click "Create Funnel Step"
6. Wait for the workspace to update and show the new step
7. Repeat for each additional page


### Phase 4: Open the Page Builder

1. Click on the first funnel step you want to build (click its name on the workspace screen)
2. Wait for the step detail view to load. You will see two boxes in the middle of the screen.
3. Click "Create from Blank"
4. WAIT AT LEAST 5 FULL SECONDS. The page builder takes time to load. Do NOT click anything during this loading period.
5. Verify the builder has loaded. You should see:
   - A canvas/editor area in the middle of the screen
   - A toolbar at the top
   - Possibly an "Ask AI" popup on the left side
6. The builder loads inside an iframe (a page within a page). Your automation needs to switch to the iframe context to interact with builder elements. Use the get_builder_frame() function from the setup.


### Phase 5: Dismiss the AI Assistant

1. If an "Ask AI" popup appears on the left side of the builder, close it by clicking the X or close button
2. You do not need this popup because you have your own HTML code
3. If the popup does not appear, that is fine - skip this step and move on
4. Do not crash or stop if the popup is absent. Handle it gracefully.


### Phase 6: Add a Blank Section and Code Element

1. Click "Blank Section" in the middle of the canvas. This adds an empty section to your page.
2. Wait for the blank section to appear (it will show as a green-bordered area)
3. Hover over the "+" icon in the middle of the blank section. The word "Add" should appear.
4. Click the "+" or "Add" button. An element selection panel will open on the left side.
5. Scroll ALL THE WAY DOWN in the left panel. Look for a section labeled "Custom" near the bottom.
6. Click "Code" under the Custom section
7. Wait for a "Custom HTML/JavaScript" element to appear in the canvas. It will show as a blue box.


### Phase 7: Set Full Width (CRITICAL STEP)

This step makes your design span the entire page width. If you skip this, your design will be trapped in a narrow column and look terrible.

1. You need to click on the SECTION container, NOT the code element. Here is how to tell them apart:
   - The BLUE border = the code element (this is NOT what you want for this step)
   - The GREEN border = the section container (this IS what you want)
2. Move your mouse slowly between the top edge of the blue code element and the edge of the section. When you see a green line or green highlight appear, click on it.
3. A settings panel will appear on the right side of the screen
4. Find the toggle labeled "Allow rows to take entire width" (it might also say "Full Width")
5. Turn this toggle ON (click it so it is enabled)
6. The section will now span the full page width


### Phase 8: Paste Your Code

1. Click on the BLUE box labeled "Custom HTML/JavaScript" in the canvas
2. The right-side panel will update to show element settings
3. Click "Open Code Editor"
4. A BLACK code editor window will open (it is a popup/overlay)
5. NOTE: Even though you clicked inside the builder iframe to open it, the code editor popup usually appears on the main page, not inside the iframe
6. Paste your ENTIRE HTML code into the editor. All of it - the HTML, the CSS (in style tags), and any JavaScript. Put it all in this one editor. Do not split it across multiple elements.
7. The GHL code editor has no character limit - you can paste as much code as you need
8. Click "Save" in the code editor
9. The code editor will close and the canvas will update to show a rendered preview of your page


### Phase 9: Save the Page

1. Find the SAVE button in the top-right of the builder. It looks like a floppy disk icon and is located next to the "Publish" button.
2. Click the save button
3. Wait for the save to complete (you may see a brief notification or the button may flash)
4. NOTE: The save button is on the main page toolbar, not inside the iframe


### Phase 10: Preview and Verify

1. Click the PREVIEW button (it looks like an eyeball icon, located next to the save button in the top-right)
2. A preview will open (either in the same window or in a new tab)
3. Check ALL of the following:
   - All sections render correctly (no broken layouts)
   - Text is readable and properly formatted
   - Colors match the brand specifications
   - Images load correctly
   - Desktop layout looks right (at full width)
   - Tablet layout looks right (resize window to about 768 pixels wide)
   - Mobile layout looks right (resize window to about 375 pixels wide)
   - Buttons are visible and properly styled
   - No horizontal scrolling on any screen size
   - No elements cut off or overlapping
   - Fonts render correctly
   - Page background extends full width

If something looks wrong, go back to Phase 8, open the code editor, fix the code, save again, and preview again.


## Deploying Multiple Pages

When you have a funnel with multiple pages (like landing page + sales page + checkout + thank you), you repeat Phases 4 through 10 for each page.

Between pages:
1. Navigate back to the funnel workspace URL you saved in Phase 2
2. Click the next step you want to build
3. Follow Phases 4 through 10 with the HTML code for that specific page

Keep track of which pages succeeded and which had issues.


## Updating an Existing Page

Sometimes you need to update a page that has already been deployed, not create a new one. The process is different:

1. Navigate to Sites, then Funnels (or Websites)
2. Find the existing funnel in the list and click on it
3. Click on the specific step/page you want to update
4. The page builder will open with the EXISTING content already loaded
5. Click on the code element (the blue "Custom HTML/JavaScript" box)
6. Click "Open Code Editor"
7. You will see the current code. Select ALL of it and DELETE it.
8. Paste the NEW updated code
9. Click Save in the code editor
10. Click the Save button (floppy disk) in the top toolbar
11. Preview to verify the changes look correct
12. Publish ONLY if the user approves

IMPORTANT: When updating, you do NOT create a new funnel or add new steps. You are editing the existing code in the existing page. Do not accidentally create a duplicate.


## The Iframe Deployment Method (For Complex Code)

Sometimes your HTML code is very complex - it may include heavy animations, JavaScript libraries, or CSS that conflicts with GHL's built-in styles. When this happens, the page may not render correctly in GHL's code block.

The solution is the iframe method:
1. Host your HTML file externally (on a CDN, your own server, or a static hosting service like Cloudflare Pages or Vercel)
2. Instead of pasting your full HTML into GHL's code block, paste a small iframe snippet that loads your hosted page
3. The iframe creates a completely isolated environment so GHL's styles cannot interfere with yours

When to use the iframe method:
- Your code includes JavaScript libraries that conflict with GHL's built-in scripts
- Your CSS is being overridden or corrupted by GHL's default styles
- You are deploying a fully self-contained web application
- The rendered output looks different in GHL than in a standalone browser
- You have tried fixing the direct code 3+ times and the problems persist

The full iframe snippet code and setup instructions are in the ghl-install-pages-full.md file, Section 9.


## Publishing (ONLY When User Approves)

NEVER publish without explicit user approval. The publishing workflow is:

1. Build all pages
2. Save all pages
3. Preview all pages and verify they render correctly
4. Send the user a deployment report (see below) with preview screenshots
5. WAIT for the user to say "go ahead" or "publish" or give explicit approval
6. ONLY THEN click "Publish" on each page
7. Verify the live URLs are working after publishing


## Deployment Report Template

After completing any deployment (new or update), send the user a report in this format:

```
DEPLOYMENT REPORT
Date: [date]
Account: [sub-account name]
Type: [New Funnel / Page Update / Multi-Page Funnel]

PAGES DEPLOYED:
| Page Name | URL Path | Status | Screenshot |
|-----------|----------|--------|------------|
| Landing Page | /landing | Deployed + Saved | [screenshot] |
| Sales Page | /sales | Deployed + Saved | [screenshot] |

VERIFICATION:
- Desktop (1440px): [Pass/Fail] - [notes]
- Tablet (768px): [Pass/Fail] - [notes]
- Mobile (375px): [Pass/Fail] - [notes]
- Horizontal scroll: [None detected / Issue on X page]

PUBLISH STATUS: [Not published - awaiting your approval / Published]

ISSUES FOUND: [None / List any issues]

NEXT STEPS:
- [Review preview screenshots]
- [Approve for publishing]
- [Any fixes needed]
```

Always include this report. Do not skip it. The user needs to know exactly what was done.
