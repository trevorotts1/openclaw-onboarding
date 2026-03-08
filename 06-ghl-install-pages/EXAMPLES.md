# GHL Install Pages - Real Examples

This document shows real examples of deploying pages into GoHighLevel (Convert and Flow) using browser automation. Each example includes what happens step by step, what the AI agent should say, and what to do when things go wrong.


## Example 1: Deploying a Single Landing Page

**The request:** "Deploy the new landing page HTML into our Convert and Flow account."

### What the AI agent does:

**Step 1 - Verify prerequisites:**
Agent: "Before I deploy, let me verify everything is ready:
- HTML code: Ready (I have the SuperDesign export)
- GHL credentials: Found in ~/clawd/secrets/.env
- Target account: BlackCEO sub-account
- Browser session: Launching Playwright with persistent context..."

**Step 2 - Log in and navigate:**
Agent: "Logged into Convert and Flow. Verified I am in the correct sub-account (BlackCEO). Navigating to Sites, then Funnels..."

**Step 3 - Create the funnel:**
Agent: "Creating new funnel: 'Soft Life Sanctuary Landing Page'
- Selected Blank Funnel template
- Entered funnel name
- Clicked Create
- Funnel workspace URL saved for reference"

**Step 4 - Add the funnel step:**
Agent: "Adding funnel step:
- Step Name: Landing Page
- Step Path: /landing
- Step created successfully"

**Step 5 - Build the page:**
Agent: "Opening the page builder...
- Builder loaded (waited 5 seconds for full load)
- Dismissed AI assistant popup
- Added blank section to canvas
- Added Code element from Custom section
- Set section to full width
- Opened code editor
- Pasted full HTML code (12,847 characters)
- Saved code editor
- Saved the page"

**Step 6 - Preview and verify:**
Agent: "Running verification at three screen sizes:

Desktop (1440px): PASS - All sections render correctly, no horizontal scroll
Tablet (768px): PASS - Layout stacks properly, text readable
Mobile (375px): PASS - Single column layout, buttons full width, no overflow

Screenshots saved for your review."

**Step 7 - Report:**
```
DEPLOYMENT REPORT
Date: March 1
Account: BlackCEO
Type: New Funnel (Single Page)

PAGES DEPLOYED:
| Page Name | URL Path | Status |
|-----------|----------|--------|
| Landing Page | /landing | Deployed + Saved |

VERIFICATION:
- Desktop (1440px): Pass
- Tablet (768px): Pass
- Mobile (375px): Pass
- Horizontal scroll: None detected

PUBLISH STATUS: Not published - awaiting your approval

NEXT STEPS:
- Review the preview screenshots
- Let me know if any changes are needed
- Say "publish" when ready to go live
```


## Example 2: Deploying a Multi-Page Funnel

**The request:** "Build a complete funnel with landing page, sales page, checkout, and thank you page."

### What the AI agent does:

**Step 1 - Create the funnel and all steps at once:**
Agent: "Creating funnel: 'Product Launch Funnel'

Adding all 4 steps:
1. Landing Page - /landing - Created
2. Sales Page - /sales - Created
3. Checkout - /checkout - Created
4. Thank You - /thank-you - Created

Funnel workspace URL saved. Now deploying each page..."

**Step 2 - Deploy each page (repeating Phases 4-10 for each):**

Agent: "Deploying page 1 of 4: Landing Page
- Builder loaded
- Code pasted and saved
- Preview verified at all 3 sizes
- PASS

Deploying page 2 of 4: Sales Page
- Builder loaded
- Code pasted and saved
- Preview verified at all 3 sizes
- PASS

Deploying page 3 of 4: Checkout
- Builder loaded
- Code pasted and saved
- Preview verified at all 3 sizes
- PASS

Deploying page 4 of 4: Thank You
- Builder loaded
- Code pasted and saved
- Preview verified at all 3 sizes
- PASS"

**Step 3 - Final report:**
```
DEPLOYMENT REPORT
Date: March 1
Account: BlackCEO
Type: Multi-Page Funnel

PAGES DEPLOYED:
| Page Name | URL Path | Status |
|-----------|----------|--------|
| Landing Page | /landing | Deployed + Saved |
| Sales Page | /sales | Deployed + Saved |
| Checkout | /checkout | Deployed + Saved |
| Thank You | /thank-you | Deployed + Saved |

VERIFICATION:
- Desktop (1440px): All 4 pages pass
- Tablet (768px): All 4 pages pass
- Mobile (375px): All 4 pages pass
- Horizontal scroll: None detected on any page

PUBLISH STATUS: Not published - awaiting your approval

NEXT STEPS:
- Review preview screenshots for each page
- Approve for publishing when ready
```


## Example 3: Handling 2FA (Two-Factor Authentication)

**What happens when the account has 2FA enabled:**

Agent: "Logging into Convert and Flow...
Email entered.
Password entered.
Clicking login...

2FA DETECTED. I need you to complete the verification.

I have paused the automation. Please look at the browser window that just opened. You will see a screen asking for a verification code.

Here is what to do:
1. Open your authenticator app on your phone (Google Authenticator, Authy, or whatever you use for this account)
2. Find the code for Convert and Flow / GoHighLevel
3. Type the 6-digit code into the field in the browser window
4. Click Verify (or Submit, or whatever the button says)

I will wait up to 5 minutes for you to complete this. Take your time.

Once you finish, I will continue the deployment automatically."

[User completes 2FA]

Agent: "2FA completed. I am now on the dashboard. Continuing with the deployment..."


## Example 4: Updating an Existing Page

**The request:** "Update the landing page with the new version of the HTML."

### What the AI agent does:

Agent: "Updating existing page (not creating a new one).

1. Navigating to Sites - Funnels
2. Found funnel: 'Soft Life Sanctuary Landing Page'
3. Clicking on step: Landing Page
4. Builder loaded with existing content
5. Clicking on the code element
6. Opening code editor
7. Clearing existing code (select all, delete)
8. Pasting new HTML code (14,203 characters)
9. Saving code editor
10. Saving page
11. Running preview verification...

Desktop (1440px): PASS
Tablet (768px): PASS
Mobile (375px): PASS

Page updated successfully. Not publishing until you approve."


## Example 5: When Something Goes Wrong (Error Recovery)

**Scenario:** The AI agent cannot find the "Code" element in the builder

Agent: "Phase 6 - Adding code element...
Clicked Blank Section - OK
Clicked Add button - OK
Scrolling to find Custom section...

WARNING: Could not find 'Code' element using any of my 4 selectors.

Attempting recovery:
- Taking screenshot of current state
- Screenshot saved: error_add_code_element.png
- The element panel appears to have a different layout than expected

Trying alternative approach:
- Searching for 'Custom HTML' instead of 'Code'
- Found it! GHL may have renamed this element.
- Clicking 'Custom HTML'
- Code element added to canvas

Continuing with Phase 7..."

**Scenario:** The page renders incorrectly after pasting code

Agent: "Preview check found an issue:

Desktop (1440px): FAIL - The header section overlaps with the navigation bar
Tablet (768px): PASS
Mobile (375px): PASS

This appears to be a CSS conflict with GHL's built-in styles. The header has position:fixed which conflicts with GHL's wrapper.

Attempting fix:
- Opening code editor
- Adding GHL-specific CSS overrides to prevent the conflict
- Saving updated code
- Re-previewing...

Desktop (1440px): PASS - Header now renders correctly
Tablet (768px): PASS
Mobile (375px): PASS

Fix applied successfully."

**Scenario:** After 3+ attempts, the direct code still does not render correctly

Agent: "I have tried fixing the rendering issue 3 times with different CSS approaches, but GHL's built-in styles keep interfering with the animation library in your code.

Switching to the iframe deployment method. This will completely isolate your code from GHL's environment.

Steps:
1. Hosting your HTML file on Cloudflare Pages
2. Uploading... done. URL: https://yoursite.pages.dev/landing.html
3. Replacing the direct code in GHL with an iframe snippet that loads the hosted page
4. Saving and previewing...

Desktop (1440px): PASS - All animations work correctly now
Tablet (768px): PASS
Mobile (375px): PASS

The iframe method solved the rendering conflict."


## Example 6: The Selector Fallback System in Action

GHL updates their user interface from time to time. When a button label changes, the AI agent's selectors need to handle it gracefully.

**What happens behind the scenes:**

```
Clicking Sites in sidebar...
  Trying selector 1: [data-testid="sites-nav"] - Not found
  Trying selector 2: [aria-label*="Sites"] - Not found
  Trying selector 3: a[href*="/sites"] - FOUND
  Used fallback selector #3

Clicking Funnels tab...
  Trying selector 1: [data-testid="funnels-tab"] - Not found
  Trying selector 2: [aria-label*="Funnels"] - FOUND
  Used fallback selector #2
```

The agent tries the most specific selector first. If that fails, it tries the next one. It keeps going through the list until one works. This means the automation keeps working even when GHL changes their button labels or HTML structure.

If ALL selectors fail for a given element, the agent takes a screenshot, logs the current state, and activates the recovery protocol.


## Example 7: Full Automation Sequence Summary

Here is the complete sequence visualized:

```
SETUP:
  Configure browser (1440x900 minimum)
  Load or create persistent session
  Handle 2FA if present (pause for manual verification)

NAVIGATION:
  Click Sites - Click Funnels tab
  Wait for funnel list to load

FUNNEL CREATION:
  New Funnel - Blank - Name - Create
  SAVE the funnel workspace URL
  Add steps for each page (name + path)

FOR EACH PAGE:
  Click step - Create from Blank - WAIT for builder to load
  Switch to builder iframe context
  Close "Ask AI" popup (if it appears)
  Add Blank Section
  Hover "+" - Click Add - Scroll down - Custom - Code
  Click GREEN border (section) - Enable full width
  Click BLUE "Custom HTML/JavaScript" - Open Code Editor
  Paste ENTIRE HTML code
  Save code editor - Save page - Preview
  Verify at 1440px, 768px, 375px

REPORTING:
  Send deployment report with screenshots
  WAIT for user approval

PUBLISHING:
  Only when user approves
  Publish each page
  Verify live URLs
```
