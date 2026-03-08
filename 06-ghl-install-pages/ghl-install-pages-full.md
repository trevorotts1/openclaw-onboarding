How to install pages in the GHL/convert in Flow pages area or funnel area. These are the exact instructions. This assumes that you already have the HTML code written, and that you are merely going over to the section within Convert and Flow that allows you to insert that HTML code into a code block.This is very important that this is understood.
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

══════════════════════════════════════════════════════════════════
  TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)
══════════════════════════════════════════════════════════════════

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Find the OpenClaw master files folder in ~/Downloads/. It may be named:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder is found, create: ~/Downloads/OpenClaw Master Files/

   Save this full document content as a .md file in that folder.

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Only add a brief summary and a file path reference to where the full
   documentation lives. Never paste thousands of lines into core files.

3. USE THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Only add what is labeled. Nothing else goes into core files.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time you execute instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE TREVOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY THESE WITHOUT PERMISSION
- API keys - copy them exactly, character for character
- Terminal commands - run them exactly as written, no edits
- Config values - use the exact values specified
- Model names - use the exact names specified, spelling matters
- File paths - use the exact paths specified
If you are unsure whether something should be changed, the answer is NO.
Ask Trevor first. Do not guess. Do not assume.

RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take. Write it out.
Show it to the user before starting. Get confirmation. Then execute.

RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE
When you believe you are finished, go back to your checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before telling the user you are done.
Do NOT tell the user you are done until the checklist is 100% complete.

RULE 6: REPORT WHAT YOU DID
When finished, give the user a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════════
Adding Convert & Flow Pages
How to Deploy Your Design Using a Browser Agent (Enhanced Edition)
Convert & Flow / Go High Level - Browser Automation Guide v2.0
This document is for AI agents (OpenClaw, Claude Code, or any autonomous agent with browser control) that need to deploy a SuperDesign HTML export into a Convert & Flow or Go High Level account using browser automation (Playwright, Puppeteer, or similar).

TABLE OF CONTENTS
Prerequisites
Browser Configuration & Viewport Setup
Session Management
Two-Factor Authentication (2FA) Handling
Understanding GHL's Iframe Architecture
Selector Strategy & Fallback Protocols
Error Recovery Framework
Step-by-Step Deployment Process (Phase 1–10)
Deploying Large/Complex Code via Iframe Method
Debugging Common Issues
Deploying Multiple Funnel Pages
Publishing (Only When User Approves)
Complete Automation Sequence (Summary)

1. PREREQUISITES
Before starting, confirm you have:
[ ] Browser automation tool installed and working (Playwright recommended)
[ ] Access to the user's Convert & Flow or GHL account (credentials or saved session)
[ ] The finished HTML code ready to paste (SuperDesign export with real content injected, all CSS inline or in <style> tags, no React, no external dependencies)
[ ] Knowledge of what pages need to be built (page names, URL paths, and which code goes where)
[ ] A fallback plan for 2FA if the account has it enabled (see Section 4)
[ ] A hosting URL for iframe deployment if the codebase is extremely complex (see Section 9)
[ ] Knowledge of which SUB-ACCOUNT to deploy into (see "Sub-Account Selection" below)

CREDENTIAL STORAGE (Where to Keep GHL Login Info)

GHL credentials must NEVER be hardcoded in scripts or committed to repositories.

Store credentials in the workspace secrets file:
~/clawd/secrets/.env

Add these lines:
GHL_EMAIL=user@email.com
GHL_PASSWORD=the-account-password

In your Playwright scripts, load them from the environment:
import os
email = os.environ.get("GHL_EMAIL")
password = os.environ.get("GHL_PASSWORD")

If the account uses SSO (single sign-on) instead of email/password, note this in your workspace files and use the persistent session approach (Section 3) where the user logs in once manually and the session is reused.

SUB-ACCOUNT SELECTION (Critical Before Phase 1)

GHL/Convert and Flow uses a two-level structure:
- AGENCY LEVEL: The top-level dashboard where you manage all clients
- SUB-ACCOUNT LEVEL: Each client has their own sub-account with separate sites, funnels, and settings

You MUST be inside the correct sub-account before building pages.

How to check which sub-account you are in:
- Look at the top-left of the GHL dashboard
- The sub-account name is displayed next to the logo
- If it says your agency name (not the client name), you are at the agency level

How to switch to the correct sub-account:
1. Click the sub-account name/dropdown in the top-left corner
2. Search for the client's sub-account name
3. Click to enter that sub-account
4. Verify you are now inside the correct sub-account (the name in the top-left should match)

Playwright code to switch sub-accounts:
# After login, check if we need to switch sub-accounts
def switch_sub_account(page, target_account_name):
    # Click the account switcher
    account_switcher_selectors = [
        '[data-testid="account-switcher"]',
        '[class*="account-select"]',
        '[class*="location-select"]',
        '.agency-selector',
        'text=' + target_account_name,
    ]
    
    # First check if we're already in the right account
    try:
        current = page.locator('[class*="account-name"], [class*="location-name"]').first.inner_text()
        if target_account_name.lower() in current.lower():
            print(f"Already in correct sub-account: {current}")
            return True
    except:
        pass
    
    # Click the switcher dropdown
    try:
        switcher = find_element_with_fallback(page, account_switcher_selectors[:4])
        switcher.click()
        page.wait_for_timeout(1000)
        
        # Search for the target account
        search_input = page.locator('input[placeholder*="search" i], input[placeholder*="filter" i]').first
        search_input.fill(target_account_name)
        page.wait_for_timeout(1000)
        
        # Click the matching account
        page.locator(f'text={target_account_name}').first.click()
        page.wait_for_timeout(2000)
        
        print(f"Switched to sub-account: {target_account_name}")
        return True
    except Exception as e:
        print(f"Could not switch sub-account: {e}")
        return False

IMPORTANT: If you deploy pages in the WRONG sub-account, the client will not see them. Always verify you are in the correct sub-account before proceeding to Phase 1.

WEBSITES vs. FUNNELS - Which One to Use

GHL has TWO places to build pages: Websites and Funnels. They use the exact same builder but serve different purposes.

When to use FUNNELS (default - use this 90% of the time):
- Landing pages, opt-in pages, sales pages, checkout pages, thank you pages
- Any multi-step flow where a visitor moves through pages in order
- Most SuperDesign exports
- When in doubt, use Funnels

When to use WEBSITES (only when specifically requested):
- Standalone pages that are NOT part of a flow (e.g., an About page, a blog)
- Full website with navigation between pages
- The user specifically says "Website" not "Funnel"

The ONLY difference in the builder process:
- Funnels: Sites sidebar -> Funnels tab -> New Funnel
- Websites: Sites sidebar -> Websites tab -> New Website

Everything else (adding pages, code blocks, saving, publishing) is identical.
If the user does not specify, DEFAULT to Funnels.

2. BROWSER CONFIGURATION & VIEWPORT SETUP
CRITICAL: GHL's builder behaves differently at different window sizes. If the agent launches a browser at 800px wide, the sidebar may collapse, elements may stack differently, and selectors will not match. You MUST set a minimum viewport size at launch.
Required Viewport Configuration
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir="./ghl_session",
        headless=False,  # Set True for headless operation
        viewport={"width": 1440, "height": 900},  # REQUIRED - minimum 1280x800
        args=[
            "--window-size=1440,900",
            "--disable-blink-features=AutomationControlled",  # Reduces detection
        ]
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
Why This Matters
Below 1280px width: GHL's left sidebar may collapse into a hamburger menu, breaking all sidebar-based selectors
Below 900px height: Modal dialogs may not fully render, cutting off buttons
Headless mode: Some GHL components render differently in headless - if you encounter issues, switch to headless=False for debugging
Recommended Settings by Use Case

3. SESSION MANAGEMENT
First-Time Login
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir="./ghl_session",
        headless=False,
        viewport={"width": 1440, "height": 900}
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    
    # Navigate to login
    page.goto("https://app.convertandflow.com/login")  # or GHL login URL
    
    # Fill credentials using robust selectors (see Section 6)
    email_field = find_element_with_fallback(page, [
        'input[name="email"]',
        'input[type="email"]',
        'input[placeholder*="email" i]',
        '#email',
    ])
    email_field.fill("user@email.com")
    
    password_field = find_element_with_fallback(page, [
        'input[name="password"]',
        'input[type="password"]',
        'input[placeholder*="password" i]',
        '#password',
    ])
    password_field.fill("password")
    
    # Click login button
    login_button = find_element_with_fallback(page, [
        'button[type="submit"]',
        'button:has-text("Log in")',
        'button:has-text("Sign in")',
        'button:has-text("Login")',
    ])
    login_button.click()
    
    # Wait for dashboard OR 2FA screen
    try:
        page.wait_for_url("**/dashboard**", timeout=10000)
        print("✅ Logged in successfully. Session saved.")
    except:
        # Check if we hit 2FA (see Section 4)
        handle_2fa_if_present(page)
Subsequent Sessions
# Session is already saved - no login needed
browser = p.chromium.launch_persistent_context(
    user_data_dir="./ghl_session",
    headless=True,
    viewport={"width": 1440, "height": 900}
)
page = browser.pages[0] if browser.pages else browser.new_page()
page.goto("https://app.convertandflow.com/dashboard")
# Should load directly to dashboard without login
If Session Expires
If the dashboard doesn't load (redirects to login), re-authenticate:
if "login" in page.url:
    print("⚠️ Session expired. Re-authenticating...")
    email_field = find_element_with_fallback(page, [
        'input[name="email"]',
        'input[type="email"]',
        'input[placeholder*="email" i]',
    ])
    email_field.fill(email)
    
    password_field = find_element_with_fallback(page, [
        'input[name="password"]',
        'input[type="password"]',
    ])
    password_field.fill(password)
    
    login_button = find_element_with_fallback(page, [
        'button[type="submit"]',
        'button:has-text("Log in")',
        'button:has-text("Sign in")',
    ])
    login_button.click()
    
    try:
        page.wait_for_url("**/dashboard**", timeout=10000)
        print("✅ Re-authenticated successfully.")
    except:
        handle_2fa_if_present(page)

4. TWO-FACTOR AUTHENTICATION (2FA) HANDLING
Many business GHL accounts have 2FA enabled. The agent MUST be prepared for this.
Detection
def handle_2fa_if_present(page):
    """
    Check if the current page is a 2FA verification screen.
    If so, pause automation and alert the user to complete verification manually.
    """
    # Common 2FA indicators - check for any of these
    twofa_indicators = [
        'input[name="code"]',
        'input[name="otp"]',
        'input[placeholder*="verification" i]',
        'input[placeholder*="code" i]',
        'text=Two-factor',
        'text=Verify your identity',
        'text=Enter the code',
        'text=Authentication code',
        'text=2FA',
    ]
    
    for selector in twofa_indicators:
        try:
            if page.locator(selector).is_visible(timeout=2000):
                print("🔐 2FA DETECTED - Manual intervention required.")
                print("⏸️  PAUSING AUTOMATION.")
                print("   → Please complete 2FA verification in the browser window.")
                print("   → The agent will resume automatically once the dashboard loads.")
                
                # Wait for user to complete 2FA - long timeout
                page.wait_for_url("**/dashboard**", timeout=300000)  # 5 minute timeout
                print("✅ 2FA completed. Resuming automation.")
                return True
        except:
            continue
    
    # If no 2FA detected but we're not on the dashboard either
    if "dashboard" not in page.url:
        print("❌ Login failed - not on dashboard and no 2FA detected.")
        print(f"   Current URL: {page.url}")
        page.screenshot(path="login_failure.png")
        print("   📸 Screenshot saved: login_failure.png")
        raise Exception("Login failed. Check credentials and screenshot.")
    
    return False
Key Rules for 2FA
NEVER attempt to bypass 2FA - always pause and wait for human intervention
Set a generous timeout - the user may need to find their phone, open an authenticator app, etc. 5 minutes is the recommended minimum
Keep the browser visible - set headless=False when 2FA might be required so the user can see and interact with the browser window
Save the session after 2FA - persistent context will remember the 2FA approval, reducing future interruptions
Log the event - always print clear instructions so the user knows what to do

5. UNDERSTANDING GHL'S IFRAME ARCHITECTURE
This is critical for any browser agent working with GHL's page builder.
GHL's page builder loads inside nested iframes. When the agent tries to click elements inside the builder canvas, standard page.click() calls will fail because the elements exist inside an iframe, not on the main page.
How GHL's Builder is Structured
Main Page (app.convertandflow.com)
├── Left Sidebar (main page - selectable normally)
├── Top Toolbar (main page - selectable normally)
└── Builder Canvas Area
    └── <iframe src="...builder...">          ← FIRST IFRAME LAYER
        └── Builder Controls
            └── <iframe src="...preview...">  ← SECOND IFRAME LAYER (preview/canvas)
                └── Your rendered HTML content
When You Need Iframe Context Switching
How to Switch Iframe Context in Playwright
def get_builder_frame(page):
    """
    Locate and return the builder iframe context.
    GHL's builder iframe can have different selectors depending on the version.
    This function tries multiple approaches.
    """
    # Approach 1: Direct iframe selector
    iframe_selectors = [
        'iframe[src*="builder"]',
        'iframe[src*="funnel"]',
        'iframe[id*="builder"]',
        'iframe[class*="builder"]',
        'iframe[title*="builder" i]',
        'iframe[name*="builder"]',
    ]
    
    for selector in iframe_selectors:
        try:
            frame = page.frame_locator(selector).first
            # Verify the frame is accessible by checking for any element
            frame.locator('body').wait_for(timeout=3000)
            print(f"✅ Builder iframe found via: {selector}")
            return frame
        except:
            continue
    
    # Approach 2: Find by frame URL content
    for frame in page.frames:
        if any(keyword in (frame.url or "") for keyword in ["builder", "funnel", "editor"]):
            print(f"✅ Builder iframe found via frame URL: {frame.url}")
            return frame
    
    # Approach 3: If no iframe found, the builder may render directly on page
    # (some GHL versions don't use iframes)
    print("⚠️ No builder iframe detected - assuming builder renders on main page.")
    return page


def click_in_builder(page, selector, builder_frame=None, timeout=5000):
    """
    Click an element that lives inside the builder iframe.
    Falls back to main page if iframe approach fails.
    """
    if builder_frame is None:
        builder_frame = get_builder_frame(page)
    
    try:
        if hasattr(builder_frame, 'locator'):
            # It's a frame_locator
            builder_frame.locator(selector).click(timeout=timeout)
        else:
            # It's a regular page or frame
            builder_frame.locator(selector).click(timeout=timeout)
        return True
    except:
        # Fallback: try on main page
        try:
            page.locator(selector).click(timeout=timeout)
            return True
        except:
            print(f"❌ Could not find element: {selector}")
            return False
Important Iframe Rules
Always check for iframes before interacting with the builder canvas - never assume elements are on the main page
The iframe context can change - if you navigate away and come back, you may need to re-acquire the iframe reference
Screenshots capture the main page by default - to screenshot what's inside the iframe, you need to use the frame's screenshot method or use full-page screenshots
Some GHL versions may not use iframes - always build fallback logic that tries the main page if iframe detection fails
The code editor modal may render on the main page - even though you clicked a builder element to open it, the modal/overlay often renders outside the iframe

6. SELECTOR STRATEGY & FALLBACK PROTOCOLS
The Problem with Text-Based Selectors
GHL updates their UI frequently. Relying solely on text=Sites or text=Funnels means your automation breaks the moment they change a label. Every selector must have fallbacks.
The Fallback Selector Function
def find_element_with_fallback(page_or_frame, selectors, timeout=5000, action="find"):
    """
    Try multiple selectors in order. Return the first one that matches a visible element.
    
    Args:
        page_or_frame: The page, frame, or frame_locator to search in
        selectors: List of CSS/text selectors to try in priority order
        timeout: How long to wait for each selector (ms)
        action: Description for logging
    
    Returns:
        The locator for the first matching visible element
    
    Raises:
        Exception if no selector matches
    """
    errors = []
    
    for i, selector in enumerate(selectors):
        try:
            locator = page_or_frame.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout)
            if i > 0:
                print(f"   ℹ️ Primary selector failed. Used fallback #{i + 1}: {selector}")
            return locator
        except Exception as e:
            errors.append(f"  Selector {i + 1} '{selector}': {str(e)[:80]}")
            continue
    
    # All selectors failed
    error_msg = f"❌ All {len(selectors)} selectors failed for '{action}':\n" + "\n".join(errors)
    print(error_msg)
    raise Exception(error_msg)
Recommended Selector Chains for Key GHL Elements
For every interactive element, provide a chain of selectors ordered from most specific to most general:
# SELECTOR REFERENCE - Update these if GHL changes their UI

SELECTORS = {
    "sidebar_sites": [
        '[data-testid="sites-nav"]',
        '[aria-label*="Sites"]',
        'a[href*="/sites"]',
        'text=Sites',
        '.sidebar >> text=Sites',
    ],
    
    "tab_funnels": [
        '[data-testid="funnels-tab"]',
        '[aria-label*="Funnels"]',
        'a[href*="funnels"]',
        'text=Funnels',
        '.nav-tabs >> text=Funnels',
        'button:has-text("Funnels")',
    ],
    
    "new_funnel_button": [
        '[data-testid="new-funnel"]',
        'button:has-text("New Funnel")',
        'button:has-text("+ New Funnel")',
        'a:has-text("New Funnel")',
        'text=New Funnel',
    ],
    
    "blank_funnel_option": [
        'text=Blank Funnel',
        'text=Blank',
        '[data-testid="blank-funnel"]',
        'button:has-text("Blank")',
        '.funnel-template >> text=Blank',
    ],
    
    "funnel_name_input": [
        'input[placeholder*="name" i]',
        'input[name="name"]',
        'input[data-testid="funnel-name"]',
        'input[aria-label*="name" i]',
        'label:has-text("Name") >> .. >> input',
    ],
    
    "create_button": [
        'button:has-text("Create")',
        'button[type="submit"]',
        '[data-testid="create-funnel"]',
        'button.btn-primary:has-text("Create")',
    ],
    
    "add_new_step": [
        'text=Add New Step',
        'button:has-text("Add New Step")',
        'button:has-text("Add Step")',
        '[data-testid="add-step"]',
        'a:has-text("Add New Step")',
    ],
    
    "step_name_input": [
        'input[placeholder*="name" i]',
        'input[name="stepName"]',
        'input[data-testid="step-name"]',
    ],
    
    "step_path_input": [
        'input[placeholder*="path" i]',
        'input[name="pathName"]',
        'input[name="path"]',
        'input[data-testid="step-path"]',
    ],
    
    "create_funnel_step": [
        'button:has-text("Create Funnel Step")',
        'button:has-text("Create Step")',
        'button.bg-black:has-text("Create")',
        '[data-testid="create-step"]',
    ],
    
    "create_from_blank": [
        'text=Create from Blank',
        'button:has-text("Create from Blank")',
        'button:has-text("Start from Blank")',
        '[data-testid="create-blank"]',
    ],
    
    "close_ai_popup": [
        '[class*="close"]',
        '[aria-label="Close"]',
        'button[aria-label="Close"]',
        '.modal-close',
        'text=Ask AI >> .. >> button',
    ],
    
    "blank_section": [
        'text=Blank Section',
        '[data-testid="blank-section"]',
        'button:has-text("Blank Section")',
        '.section-blank',
    ],
    
    "add_element_button": [
        '[class*="add"]',
        '[title="Add"]',
        '[aria-label="Add"]',
        'button:has-text("Add")',
        '.add-element',
    ],
    
    "code_element": [
        'text=Code',
        '[data-testid="code-element"]',
        'text=Custom Code',
        '.element-code',
    ],
    
    "custom_html_block": [
        'text=Custom HTML/JavaScript',
        'text=Custom HTML',
        'text=Custom Code',
        '[data-testid="custom-code"]',
    ],
    
    "open_code_editor": [
        'text=Open Code Editor',
        'button:has-text("Open Code Editor")',
        'button:has-text("Edit Code")',
        '[data-testid="open-editor"]',
    ],
    
    "code_editor_textarea": [
        'textarea',
        '[class*="code-editor"]',
        '[class*="monaco"]',
        '[class*="CodeMirror"]',
        '[role="textbox"]',
    ],
    
    "save_code_editor": [
        'text=Save',
        'button:has-text("Save")',
        '[data-testid="save-code"]',
    ],
    
    "save_page_button": [
        '[title*="Save"]',
        '[aria-label*="Save"]',
        'button:has-text("Save")',
        '[data-testid="save-page"]',
        '.save-btn',
    ],
    
    "preview_button": [
        '[title*="Preview"]',
        '[aria-label*="Preview"]',
        'button:has-text("Preview")',
        '[data-testid="preview"]',
        '.preview-btn',
    ],
    
    "publish_button": [
        '[title*="Publish"]',
        '[aria-label*="Publish"]',
        'button:has-text("Publish")',
        '[data-testid="publish"]',
    ],
    
    "full_width_toggle": [
        'text=Allow rows to take entire width',
        'text=Full Width',
        '[data-testid="full-width-toggle"]',
        'label:has-text("full width") >> .. >> input[type="checkbox"]',
        'label:has-text("entire width") >> .. >> input[type="checkbox"]',
    ],
}
Using the Selector Reference
# Instead of this (fragile):
page.click('text=Sites')

# Do this (robust):
sites_link = find_element_with_fallback(page, SELECTORS["sidebar_sites"])
sites_link.click()

7. ERROR RECOVERY FRAMEWORK
The Retry Wrapper
Every significant action should be wrapped in retry logic. If an element is not found, the agent should not crash - it should retry, screenshot, and report.
import time

def retry_action(action_fn, max_retries=3, delay=2, action_name="action"):
    """
    Retry an action up to max_retries times with delay between attempts.
    Takes a screenshot on failure for debugging.
    
    Args:
        action_fn: A callable that performs the action (should raise on failure)
        max_retries: Number of retry attempts
        delay: Seconds between retries
        action_name: Human-readable name for logging
    
    Returns:
        The return value of action_fn if successful
    
    Raises:
        Exception after all retries exhausted
    """
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            result = action_fn()
            if attempt > 1:
                print(f"   ✅ {action_name} succeeded on attempt {attempt}")
            return result
        except Exception as e:
            last_error = e
            print(f"   ⚠️ {action_name} - attempt {attempt}/{max_retries} failed: {str(e)[:100]}")
            
            if attempt < max_retries:
                print(f"   ⏳ Retrying in {delay}s...")
                time.sleep(delay)
            else:
                # Final attempt failed - screenshot and raise
                try:
                    page.screenshot(path=f"error_{action_name.replace(' ', '_')}.png")
                    print(f"   📸 Error screenshot saved: error_{action_name.replace(' ', '_')}.png")
                except:
                    pass
    
    raise Exception(f"❌ {action_name} failed after {max_retries} attempts. Last error: {last_error}")
Usage Example
# Wrapping a navigation action in retry logic
retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["sidebar_sites"]).click(),
    max_retries=3,
    delay=2,
    action_name="Click Sites in sidebar"
)
The Safe Wait Function
GHL pages load asynchronously. Instead of using fixed wait_for_timeout() calls, wait for specific conditions:
def safe_wait(page, condition_fn, timeout=10000, poll_interval=500, description="condition"):
    """
    Wait for a condition to become true, polling at regular intervals.
    More reliable than fixed timeouts.
    """
    start = time.time()
    while (time.time() - start) * 1000 < timeout:
        try:
            if condition_fn():
                return True
        except:
            pass
        time.sleep(poll_interval / 1000)
    
    print(f"⚠️ Timed out waiting for: {description}")
    return False


# Usage examples:

# Wait for the funnel list to load
safe_wait(page, lambda: page.locator('.funnel-list, [data-testid="funnel-list"]').count() > 0,
          description="funnel list to load")

# Wait for the builder to fully render
safe_wait(page, lambda: page.locator('iframe[src*="builder"]').count() > 0,
          description="builder iframe to load")
The Recovery Protocol
When something goes truly wrong and retries are not enough:
def recovery_protocol(page, step_name, error):
    """
    Execute when all retries fail. Takes screenshot, logs state, and
    provides instructions for manual intervention or restart.
    """
    print(f"\n{'='*60}")
    print(f"🚨 RECOVERY PROTOCOL ACTIVATED")
    print(f"   Failed Step: {step_name}")
    print(f"   Error: {str(error)[:200]}")
    print(f"   Current URL: {page.url}")
    print(f"{'='*60}")
    
    # Take full-page screenshot
    screenshot_path = f"recovery_{step_name.replace(' ', '_')}_{int(time.time())}.png"
    page.screenshot(path=screenshot_path, full_page=True)
    print(f"   📸 Full screenshot saved: {screenshot_path}")
    
    # Log page state
    print(f"   📋 Page title: {page.title()}")
    print(f"   📋 Visible text (first 500 chars): {page.inner_text('body')[:500]}")
    
    # Check for common recovery scenarios
    if "login" in page.url:
        print("   🔑 Detected login page - session may have expired.")
        print("   → Attempting re-authentication...")
        return "REAUTH"
    
    if "error" in page.url or "404" in page.inner_text('body'):
        print("   🔍 Detected error page.")
        print("   → Attempting navigation back to dashboard...")
        page.goto("https://app.convertandflow.com/dashboard")
        return "RESTART"
    
    print("   ⏸️ PAUSING - Manual intervention may be required.")
    print("   → Review the screenshot and current page state.")
    print("   → The agent will wait for the page to stabilize...")
    
    # Wait a bit and check if page recovers
    page.wait_for_timeout(5000)
    return "MANUAL"

8. STEP-BY-STEP DEPLOYMENT PROCESS
Phase 1: Navigate to Funnels
ACTION: Click "Sites" in the left sidebar
SELECTORS: Use SELECTORS["sidebar_sites"] chain
WAIT: Page content updates to show Sites section

ACTION: Click "Funnels" tab at the top
SELECTORS: Use SELECTORS["tab_funnels"] chain
NOTE: 90% of the time you want "Funnels" - only use "Websites" if user specifically
      requested a standalone website (not a funnel)
WAIT: Funnel list loads

# Playwright - Phase 1
retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["sidebar_sites"]).click(),
    action_name="Click Sites sidebar"
)
page.wait_for_timeout(1500)

retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["tab_funnels"]).click(),
    action_name="Click Funnels tab"
)

# Wait for funnel list to load (not just a timeout)
safe_wait(page, lambda: page.locator('.funnel-list, [class*="funnel"]').count() > 0,
          timeout=5000, description="funnel list load")
page.wait_for_timeout(1000)  # Extra buffer for async content
Phase 2: Create a New Funnel
ACTION: Click "+ New Funnel" button
LOCATION: Top right area of the page
SELECTORS: Use SELECTORS["new_funnel_button"] chain
WAIT: Modal/popup appears with funnel creation options

ACTION: Select "Blank Funnel"
OPTIONS SHOWN: Blank Funnel, AI, From Templates
CHOOSE: Blank Funnel (ALWAYS - you have your own code)
SELECTORS: Use SELECTORS["blank_funnel_option"] chain
WAIT: Name input field appears

ACTION: Type the funnel name
VALUE: Descriptive name aligned with the project
       (e.g., "Soft Life Sanctuary Landing Page")
SELECTORS: Use SELECTORS["funnel_name_input"] chain

ACTION: Click "Create"
SELECTORS: Use SELECTORS["create_button"] chain
WAIT: Funnel workspace screen loads (may take 3-5 seconds)

⚠️ CRITICAL: After funnel creation, CAPTURE AND STORE the funnel workspace URL.
You will need this URL when deploying multiple pages.

# Playwright - Phase 2
retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["new_funnel_button"]).click(),
    action_name="Click New Funnel"
)
page.wait_for_timeout(1500)

retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["blank_funnel_option"]).click(),
    action_name="Select Blank Funnel"
)
page.wait_for_timeout(1000)

name_input = find_element_with_fallback(page, SELECTORS["funnel_name_input"])
name_input.fill("Soft Life Sanctuary Landing Page")

retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["create_button"]).click(),
    action_name="Click Create"
)
page.wait_for_timeout(3000)

# CRITICAL: Capture the funnel workspace URL for multi-page deployment
funnel_workspace_url = page.url
print(f"📍 Funnel workspace URL saved: {funnel_workspace_url}")
Phase 3: Add Funnel Steps
Repeat this block for EACH page in the funnel.
ACTION: Click "Add New Step"
LOCATION: On the workspace screen
SELECTORS: Use SELECTORS["add_new_step"] chain
WAIT: Step creation form appears

ACTION: Fill in Step Name
VALUE: Page-appropriate name
       (e.g., "Landing Page", "Sales Page", "Checkout", "Thank You")
SELECTORS: Use SELECTORS["step_name_input"] chain

ACTION: Fill in Step Path
VALUE: URL-friendly path with hyphens, lowercase
       (e.g., "/landing", "/sales-page", "/checkout", "/thank-you")
SELECTORS: Use SELECTORS["step_path_input"] chain
RULE: Must be unique within this funnel

ACTION: Click "Create Funnel Step"
SELECTORS: Use SELECTORS["create_funnel_step"] chain
WAIT: Workspace updates showing the new step

# Playwright - Phase 3: Creating funnel steps
# Repeat this block for each page
pages_to_create = [
    {"name": "Landing Page", "path": "/landing"},
    {"name": "Sales Page", "path": "/sales"},
    {"name": "Checkout", "path": "/checkout"},
    {"name": "Thank You", "path": "/thank-you"},
]

for step in pages_to_create:
    retry_action(
        lambda: find_element_with_fallback(page, SELECTORS["add_new_step"]).click(),
        action_name=f"Click Add New Step for {step['name']}"
    )
    page.wait_for_timeout(1000)
    
    step_name_input = find_element_with_fallback(page, SELECTORS["step_name_input"])
    step_name_input.fill(step["name"])
    
    step_path_input = find_element_with_fallback(page, SELECTORS["step_path_input"])
    step_path_input.fill(step["path"])
    
    retry_action(
        lambda: find_element_with_fallback(page, SELECTORS["create_funnel_step"]).click(),
        action_name=f"Create step: {step['name']}"
    )
    page.wait_for_timeout(2000)
    print(f"   ✅ Step created: {step['name']} → {step['path']}")
Phase 4: Open the Page Builder
ACTION: Click on the first funnel step you want to build
WAIT: Step detail view loads - you'll see two boxes in the middle

ACTION: Click "Create from Blank"
SELECTORS: Use SELECTORS["create_from_blank"] chain
WAIT: ⚠️ WAIT AT LEAST 5 FULL SECONDS - The page builder takes time to load.
      DO NOT click anything during this loading period.
      Use safe_wait to detect when the builder has actually loaded.

VERIFY: The builder interface has loaded - you should see:
- A canvas/editor area in the middle
- A toolbar at the top
- The "Ask AI" popup on the left side (may or may not appear)

# Playwright - Phase 4
# Click on the specific step (use the step name as text selector)
step_name = "Landing Page"  # The step you want to build
retry_action(
    lambda: page.locator(f'text={step_name}').first.click(),
    action_name=f"Click step: {step_name}"
)
page.wait_for_timeout(2000)

retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["create_from_blank"]).click(),
    action_name="Click Create from Blank"
)

# CRITICAL: Wait for builder to fully load - not just a fixed timeout
# Try to detect the builder iframe or canvas
builder_loaded = safe_wait(
    page,
    lambda: (
        page.locator('iframe[src*="builder"]').count() > 0 or
        page.locator('[class*="builder"]').count() > 0 or
        page.locator('[class*="canvas"]').count() > 0
    ),
    timeout=15000,
    description="builder to load"
)

if not builder_loaded:
    print("⚠️ Builder may not have loaded. Waiting additional 5 seconds...")
    page.wait_for_timeout(5000)

# Get the builder frame reference for subsequent actions
builder_frame = get_builder_frame(page)
print("✅ Builder loaded. Frame context acquired.")
Phase 5: Dismiss the AI Assistant
ACTION: Close the "Ask AI" popup
LOCATION: Left side of the builder - look for a popup/panel labeled "Ask AI"
SELECTORS: Use SELECTORS["close_ai_popup"] chain
REASON: You don't need it - you have your own code
WAIT: Popup closes, canvas is clear
NOTE: This popup may not always appear - handle gracefully

# Playwright - Phase 5
# The AI popup may or may not appear - don't crash if it's absent
try:
    close_btn = find_element_with_fallback(
        builder_frame if builder_frame != page else page,
        SELECTORS["close_ai_popup"],
        timeout=3000
    )
    close_btn.click()
    print("   ✅ AI popup dismissed.")
except:
    print("   ℹ️ AI popup not found - skipping. (This is normal.)")
page.wait_for_timeout(500)
Phase 6: Add Blank Section + Code Element
ACTION: Click "Blank Section" in the middle of the canvas
NOTE: This element may be inside the builder iframe - use builder_frame context
WAIT: A blank section (green-bordered area) appears on the canvas

ACTION: Hover over the "+" icon in the middle of the blank section
RESULT: The word "Add" appears
ACTION: Click the "+" / "Add" button
WAIT: Element selection panel opens on the left side

ACTION: Scroll ALL the way down in the left panel
TARGET: Find the section labeled "Custom"
ACTION: Click "Code" under the Custom section
WAIT: A "Custom HTML/JavaScript" element (blue box) appears in the canvas

# Playwright - Phase 6
# These actions happen INSIDE the builder frame

# Click Blank Section
retry_action(
    lambda: click_in_builder(page, 'text=Blank Section', builder_frame),
    action_name="Click Blank Section"
)
page.wait_for_timeout(1500)

# Find and click the Add button in the section
retry_action(
    lambda: click_in_builder(
        page,
        '[class*="add"], [title="Add"], [aria-label="Add"], button:has-text("Add")',
        builder_frame
    ),
    action_name="Click Add element button"
)
page.wait_for_timeout(1000)

# Scroll down in the element panel to find Custom section
# The element panel may be on the main page or in the builder frame
try:
    # Try scrolling within the builder frame
    if hasattr(builder_frame, 'evaluate'):
        builder_frame.evaluate(
            'document.querySelector("[class*=element-panel], [class*=sidebar], [class*=panel]")?.scrollTo(0, 9999)'
        )
    else:
        page.evaluate(
            'document.querySelector("[class*=element-panel], [class*=sidebar], [class*=panel]")?.scrollTo(0, 9999)'
        )
except:
    # Fallback: scroll the entire page
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
page.wait_for_timeout(500)

# Click Code element
retry_action(
    lambda: click_in_builder(page, 'text=Code', builder_frame),
    action_name="Click Code element"
)
page.wait_for_timeout(1500)
print("   ✅ Code element added to canvas.")
Phase 7: Set Full Width (CRITICAL STEP)
This step ensures your design spans the entire page width. If you skip this, your design will be confined to a narrow column.
ACTION: Find the SECTION container (green border) - NOT the code element (blue border)
TECHNIQUE: Move your mouse slowly between elements on the canvas
- The BLUE border = the code element (not what you want here)
- The GREEN border = the section container (this is what you need)
- Hover in the area between the top edge of the code element and the section boundary
- When the GREEN line/highlight appears, click on it

ACTION: Click on the green line/border
RESULT: The SECTION settings panel opens on the right side

ACTION: Find "Allow rows to take entire width" toggle
LOCATION: In the right-side section settings panel
SELECTORS: Use SELECTORS["full_width_toggle"] chain
ACTION: Turn this toggle ON (enabled)
RESULT: The section will now span the full page width

# Playwright - Phase 7
# This is the trickiest part - finding the SECTION container vs the code element

# Strategy: Click near the top edge of the section area to select the section container
# The section wrapper typically has identifiable class names
section_selectors = [
    '[class*="section-wrapper"]',
    '[class*="row-wrapper"]',
    '[class*="section-container"]',
    '[data-testid*="section"]',
]

section_clicked = False
for selector in section_selectors:
    try:
        if hasattr(builder_frame, 'locator'):
            section = builder_frame.locator(selector).first
        else:
            section = page.locator(selector).first
        
        # Click near the top-left edge to select the section, not the element inside it
        section.click(position={"x": 5, "y": 5}, timeout=3000)
        section_clicked = True
        print(f"   ✅ Section selected via: {selector}")
        break
    except:
        continue

if not section_clicked:
    # Fallback: try clicking in the gap above the code element
    print("   ⚠️ Could not find section via selectors. Trying positional click...")
    try:
        code_element = find_element_with_fallback(
            builder_frame if builder_frame != page else page,
            SELECTORS["custom_html_block"]
        )
        box = code_element.bounding_box()
        if box:
            # Click 20px above the code element to hit the section wrapper
            page.mouse.click(box["x"] + 10, box["y"] - 20)
            section_clicked = True
    except:
        pass

if not section_clicked:
    print("   ❌ Could not select section container. Full-width may not be set.")
    print("   → Manual intervention may be needed for this step.")

page.wait_for_timeout(1000)

# Find and toggle the full-width setting
# The toggle is in the right-side settings panel (usually on the main page, not in iframe)
try:
    full_width = find_element_with_fallback(page, SELECTORS["full_width_toggle"], timeout=3000)
    
    # Check if it's already enabled
    toggle = full_width.locator('.. >> input[type="checkbox"], [role="switch"]').first
    is_checked = toggle.is_checked() if toggle.count() > 0 else False
    
    if not is_checked:
        toggle.click()
        print("   ✅ Full width toggle enabled.")
    else:
        print("   ℹ️ Full width toggle already enabled.")
except:
    print("   ⚠️ Could not find full-width toggle via selectors.")
    print("   → Attempting alternative: look for toggle by label text...")
    try:
        page.locator('label:has-text("width")').first.click()
        print("   ✅ Full width toggle clicked via label.")
    except:
        print("   ❌ Full width toggle not found. This may need manual setup.")

page.wait_for_timeout(500)
Phase 8: Paste Your Code
ACTION: Click on the BLUE box labeled "Custom HTML/JavaScript" in the canvas
WAIT: Right-side panel updates to show element settings
NOTE: The code element is inside the builder iframe, but the settings panel
      and code editor modal may render on the main page

ACTION: Click "Open Code Editor"
SELECTORS: Use SELECTORS["open_code_editor"] chain
WAIT: A BLACK code editor window opens (modal/overlay)
NOTE: The code editor modal typically renders on the MAIN PAGE (not in the iframe)
      even though you clicked an element inside the iframe to open it

ACTION: Paste the ENTIRE HTML code into the editor
CONTENT: Your complete SuperDesign HTML export - all HTML, CSS (<style> tags),
         and any JavaScript
RULE: Paste ALL of it into this single editor. Do not split across multiple elements.
NOTE: The GHL code editor has no character limitation - you can paste the full
      codebase regardless of size.

ACTION: Click "Save" in the code editor
SELECTORS: Use SELECTORS["save_code_editor"] chain
WAIT: Code editor closes, canvas updates to show rendered preview

# Playwright - Phase 8

# Click the code element (inside builder frame)
retry_action(
    lambda: click_in_builder(page, 'text=Custom HTML/JavaScript', builder_frame),
    action_name="Click Custom HTML/JavaScript element"
)
page.wait_for_timeout(1000)

# Open code editor - the button may be on the main page (right panel)
retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["open_code_editor"]).click(),
    action_name="Click Open Code Editor"
)
page.wait_for_timeout(2000)

# The code editor modal renders on the MAIN PAGE
# Find the editor textarea/input area
code_editor = find_element_with_fallback(page, SELECTORS["code_editor_textarea"])

# Clear existing content and paste new code
code_editor.fill("")  # Clear any existing code
page.wait_for_timeout(300)

# Paste the full HTML code
# Method 1: Direct fill (works for most cases)
try:
    code_editor.fill(html_code)
    print("   ✅ Code pasted via fill() method.")
except:
    # Method 2: Use JavaScript evaluation for complex content
    # This handles special characters and very large code blocks better
    print("   ⚠️ fill() failed. Using JavaScript evaluation...")
    try:
        page.evaluate("""
            (code) => {
                const editor = document.querySelector('textarea, [class*="code-editor"], [class*="monaco"], [role="textbox"]');
                if (editor) {
                    if (editor.tagName === 'TEXTAREA') {
                        editor.value = code;
                        editor.dispatchEvent(new Event('input', { bubbles: true }));
                        editor.dispatchEvent(new Event('change', { bubbles: true }));
                    } else {
                        // Monaco or CodeMirror editor
                        editor.innerText = code;
                        editor.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            }
        """, html_code)
        print("   ✅ Code pasted via JavaScript evaluation.")
    except:
        # Method 3: Use clipboard
        print("   ⚠️ JS eval failed. Using clipboard paste...")
        page.evaluate(f"navigator.clipboard.writeText(`{html_code}`)")
        code_editor.click()
        page.keyboard.press("Control+A")  # Select all existing content
        page.keyboard.press("Control+V")  # Paste from clipboard
        print("   ✅ Code pasted via clipboard.")

page.wait_for_timeout(1000)

# Save the code editor
retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["save_code_editor"]).click(),
    action_name="Save code editor"
)
page.wait_for_timeout(2000)
print("   ✅ Code saved in editor.")
Phase 9: Save the Page
ACTION: Click the SAVE button in the top-right of the builder
ICON: Floppy disk icon - located next to the "Publish" button
SELECTORS: Use SELECTORS["save_page_button"] chain
NOTE: The save button is on the MAIN PAGE (top toolbar), not inside the iframe
WAIT: Save confirmation (brief notification or visual indicator)

# Playwright - Phase 9
# The save button is on the main page toolbar (not inside the builder iframe)
retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["save_page_button"]).click(),
    action_name="Save page"
)
page.wait_for_timeout(2000)
print("   ✅ Page saved.")
Phase 10: Preview and Verify
ACTION: Click the PREVIEW button (eyeball icon)
ICON: Eye/eyeball icon - located next to the save button in the top-right
SELECTORS: Use SELECTORS["preview_button"] chain
NOTE: The preview button is on the MAIN PAGE (top toolbar)
WAIT: A preview window or new tab opens showing the live page

VERIFY - Check ALL of the following:
□ All sections render correctly (no broken layouts)
□ Text is readable and properly formatted
□ Colors match brand specifications
□ Images load (or show proper placeholder indicators)
□ Desktop layout is correct (check at 1200px+ width)
□ Tablet layout is correct (resize to ~768px width)
□ Mobile layout is correct (resize to ~375px width)
□ CTA buttons are visible and properly styled
□ No horizontal scrolling on any device size
□ No elements cut off or overlapping
□ Fonts render correctly
□ Page background extends full width

# Playwright - Phase 10
retry_action(
    lambda: find_element_with_fallback(page, SELECTORS["preview_button"]).click(),
    action_name="Click Preview"
)
page.wait_for_timeout(3000)

# Switch to preview tab if it opened in a new tab
if len(page.context.pages) > 1:
    preview_page = page.context.pages[-1]
    print("   ℹ️ Preview opened in new tab.")
else:
    preview_page = page
    print("   ℹ️ Preview opened in same window.")

# Verify rendering at different viewport widths
verification_results = {}
for width, label in [(1440, "Desktop"), (768, "Tablet"), (375, "Mobile")]:
    preview_page.set_viewport_size({"width": width, "height": 900})
    preview_page.wait_for_timeout(1500)
    
    # Take screenshot
    screenshot_path = f"preview_{label}_{width}px.png"
    preview_page.screenshot(path=screenshot_path, full_page=True)
    
    # Basic checks
    has_horizontal_scroll = preview_page.evaluate(
        'document.documentElement.scrollWidth > document.documentElement.clientWidth'
    )
    
    verification_results[label] = {
        "screenshot": screenshot_path,
        "horizontal_scroll": has_horizontal_scroll,
        "viewport": f"{width}px"
    }
    
    if has_horizontal_scroll:
        print(f"   ⚠️ {label} ({width}px): Horizontal scroll detected!")
    else:
        print(f"   ✅ {label} ({width}px): No horizontal scroll. Screenshot saved.")

print(f"\n📸 Verification screenshots saved:")
for label, result in verification_results.items():
    status = "⚠️ ISSUE" if result["horizontal_scroll"] else "✅ OK"
    print(f"   {status} {label}: {result['screenshot']}")

9. DEPLOYING LARGE/COMPLEX CODE VIA IFRAME METHOD
When to Use the Iframe Method
Sometimes your HTML codebase is extremely complex - it may include heavy animations, multiple JavaScript libraries, interactive components, or sophisticated CSS that conflicts with GHL's built-in styles. In these cases, deploying the code directly in GHL's code block may cause rendering issues because GHL's own CSS and JavaScript can interfere.
The iframe method solves this by encapsulating your entire page inside an iframe, completely isolating it from GHL's environment.
Use the iframe method when:
Your code includes JavaScript libraries that conflict with GHL's built-in scripts
Your CSS is being overridden or corrupted by GHL's default styles
You're deploying a fully self-contained web application (not just a static page)
The rendered output looks different in GHL than it does in a standalone browser
You need complete style and script isolation
How the Iframe Method Works
Instead of pasting your full HTML directly into GHL's code block, you:
Host your HTML file externally (on a CDN, your own server, or a static hosting service)
Paste a small iframe snippet into GHL's code block that loads your hosted page
The iframe creates a completely isolated environment - GHL cannot interfere with your styles or scripts
Step 1: Host Your HTML File
Your HTML file needs a publicly accessible URL. Common hosting options:
Step 2: The Iframe Snippet
Paste this code into GHL's code block (Phase 8) instead of your full HTML:
<style>
    /* Reset GHL's default spacing */
    html, body {
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
    }
    
    .external-page-wrapper {
        width: 100%;
        min-height: 100vh;
        margin: 0;
        padding: 0;
        overflow: hidden;
    }
    
    .external-page-wrapper iframe {
        width: 100%;
        height: 100vh;
        border: none;
        display: block;
        margin: 0;
        padding: 0;
    }
</style>

<div class="external-page-wrapper">
    <iframe 
        src="YOUR_HOSTED_URL_HERE"
        title="Page Content"
        scrolling="auto"
        allowfullscreen
        loading="eager"
        style="width: 100%; height: 100vh; border: none;"
    ></iframe>
</div>

<script>
    // Auto-resize iframe to match content height
    // This prevents double scrollbars
    (function() {
        const iframe = document.querySelector('.external-page-wrapper iframe');
        
        // Method 1: Listen for messages from the iframe
        window.addEventListener('message', function(event) {
            if (event.data && event.data.type === 'resize') {
                iframe.style.height = event.data.height + 'px';
            }
        });
        
        // Method 2: Poll for height changes (fallback)
        // Only works if iframe is same-origin
        function tryResize() {
            try {
                const body = iframe.contentDocument?.body;
                if (body) {
                    const height = Math.max(
                        body.scrollHeight,
                        body.offsetHeight,
                        body.clientHeight
                    );
                    if (height > 100) {
                        iframe.style.height = height + 'px';
                    }
                }
            } catch (e) {
                // Cross-origin - can't access content. Use fixed height or message API.
            }
        }
        
        iframe.addEventListener('load', function() {
            tryResize();
            // Re-check after dynamic content loads
            setTimeout(tryResize, 1000);
            setTimeout(tryResize, 3000);
        });
    })();
</script>
Step 3: Enable Auto-Resize from Your Hosted Page (Optional but Recommended)
If your hosted page has dynamic content that changes height (accordions, tabs, etc.), add this script to your hosted HTML file so it communicates its height to the parent GHL page:
<!-- Add this to your hosted HTML file, just before </body> -->
<script>
    function sendHeight() {
        const height = Math.max(
            document.body.scrollHeight,
            document.body.offsetHeight,
            document.documentElement.scrollHeight
        );
        window.parent.postMessage({ type: 'resize', height: height }, '*');
    }
    
    // Send height on load
    window.addEventListener('load', sendHeight);
    
    // Send height on resize
    window.addEventListener('resize', sendHeight);
    
    // Send height periodically for dynamic content
    setInterval(sendHeight, 2000);
    
    // Send height on any DOM mutation
    const observer = new MutationObserver(sendHeight);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true });
</script>
Step 4: Deploy in GHL Using the Standard Process
Follow the standard Phase 1–10 process, but in Phase 8, paste the iframe snippet (from Step 2 above) instead of your full HTML. Replace YOUR_HOSTED_URL_HERE with the actual URL of your hosted page.
Iframe Method vs. Direct Code - Decision Guide
Automating the Iframe Deployment
# Playwright - Automated iframe deployment
# Replace the html_code variable in Phase 8 with the iframe snippet

hosted_url = "https://yoursite.pages.dev/landing-page.html"

iframe_snippet = f"""
<style>
    html, body {{
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
    }}
    .external-page-wrapper {{
        width: 100%;
        min-height: 100vh;
        margin: 0;
        padding: 0;
        overflow: hidden;
    }}
    .external-page-wrapper iframe {{
        width: 100%;
        height: 100vh;
        border: none;
        display: block;
        margin: 0;
        padding: 0;
    }}
</style>
<div class="external-page-wrapper">
    <iframe 
        src="{hosted_url}"
        title="Page Content"
        scrolling="auto"
        allowfullscreen
        loading="eager"
        style="width: 100%; height: 100vh; border: none;"
    ></iframe>
</div>
<script>
    (function() {{
        const iframe = document.querySelector('.external-page-wrapper iframe');
        window.addEventListener('message', function(event) {{
            if (event.data && event.data.type === 'resize') {{
                iframe.style.height = event.data.height + 'px';
            }}
        }});
        iframe.addEventListener('load', function() {{
            try {{
                const body = iframe.contentDocument?.body;
                if (body) {{
                    const height = Math.max(body.scrollHeight, body.offsetHeight, body.clientHeight);
                    if (height > 100) iframe.style.height = height + 'px';
                }}
            }} catch (e) {{}}
        }});
    }})();
</script>
"""

# Now use iframe_snippet as your html_code in Phase 8
html_code = iframe_snippet

10. DEBUGGING COMMON ISSUES
If the Page Doesn't Render Correctly
STEP 1: Identify the problem
- Take a screenshot of what's wrong
- Note specific issues: layout broken? Styles missing? Elements overlapping?

STEP 2: Go back to the code editor
- Click on the code element in the builder
- Click "Open Code Editor"
- Copy the current code

STEP 3: Fix the code
- Send the code + error description to Claude Opus 4.6
  (or best available thinking model)
- Ask: "This HTML code was pasted into a Go High Level code block element
  but isn't rendering correctly. [Describe the specific issue].
  Fix the code to work within GHL's code block constraints."
- Receive the fixed code

STEP 4: Replace and test
- Paste the fixed code back into the code editor
- Click Save
- Save the page (floppy disk)
- Preview again (eyeball)
- Verify the fix worked

STEP 5: Repeat if needed
- Debug iteratively until the page renders correctly

STEP 6: If direct code keeps failing - switch to iframe method
- If you've made 3+ attempts to fix rendering issues with direct code
  and problems persist, deploy using the iframe method (Section 9)
- Host the HTML externally and use the iframe snippet instead
- This eliminates GHL style/script conflicts entirely
Common Issues & Fixes

11. DEPLOYING MULTIPLE FUNNEL PAGES
When building a full funnel (e.g., opt-in → sales → checkout → thank you), repeat the page building process for each step.
CRITICAL: You need the funnel workspace URL captured in Phase 2.
# Full funnel deployment loop
funnel_pages = {
    "Landing Page": landing_page_html,
    "Sales Page": sales_page_html,
    "Checkout": checkout_html,
    "Thank You": thank_you_html,
}

# Use the URL captured during Phase 2
# funnel_workspace_url was saved earlier

deployment_results = {}

for step_name, html_code in funnel_pages.items():
    print(f"\n{'='*50}")
    print(f"🔨 Deploying: {step_name}")
    print(f"{'='*50}")
    
    try:
        # Navigate back to funnel workspace
        page.goto(funnel_workspace_url)
        page.wait_for_timeout(2000)
        
        # Click the specific step
        retry_action(
            lambda name=step_name: page.locator(f'text={name}').first.click(),
            action_name=f"Click step: {step_name}"
        )
        page.wait_for_timeout(2000)
        
        # Execute Phases 4-10 for this page
        # Phase 4: Open builder
        retry_action(
            lambda: find_element_with_fallback(page, SELECTORS["create_from_blank"]).click(),
            action_name="Create from Blank"
        )
        
        # Wait for builder to load
        builder_loaded = safe_wait(
            page,
            lambda: (
                page.locator('iframe[src*="builder"]').count() > 0 or
                page.locator('[class*="builder"]').count() > 0
            ),
            timeout=15000,
            description="builder load"
        )
        if not builder_loaded:
            page.wait_for_timeout(5000)
        
        builder_frame = get_builder_frame(page)
        
        # Phase 5: Dismiss AI popup
        try:
            close_btn = find_element_with_fallback(
                builder_frame if builder_frame != page else page,
                SELECTORS["close_ai_popup"],
                timeout=3000
            )
            close_btn.click()
        except:
            pass
        
        # Phase 6: Add blank section + code element
        retry_action(
            lambda: click_in_builder(page, 'text=Blank Section', builder_frame),
            action_name="Blank Section"
        )
        page.wait_for_timeout(1500)
        
        retry_action(
            lambda: click_in_builder(
                page,
                '[class*="add"], [title="Add"], [aria-label="Add"]',
                builder_frame
            ),
            action_name="Add button"
        )
        page.wait_for_timeout(1000)
        
        # Scroll and click Code
        try:
            page.evaluate(
                'document.querySelector("[class*=element-panel], [class*=panel]")?.scrollTo(0, 9999)'
            )
        except:
            pass
        page.wait_for_timeout(500)
        
        retry_action(
            lambda: click_in_builder(page, 'text=Code', builder_frame),
            action_name="Code element"
        )
        page.wait_for_timeout(1500)
        
        # Phase 7: Set full width
        for selector in ['[class*="section-wrapper"]', '[class*="row-wrapper"]']:
            try:
                if hasattr(builder_frame, 'locator'):
                    builder_frame.locator(selector).first.click(position={"x": 5, "y": 5}, timeout=3000)
                else:
                    page.locator(selector).first.click(position={"x": 5, "y": 5}, timeout=3000)
                break
            except:
                continue
        page.wait_for_timeout(1000)
        
        try:
            toggle = find_element_with_fallback(page, SELECTORS["full_width_toggle"], timeout=3000)
            toggle_input = toggle.locator('.. >> input[type="checkbox"], [role="switch"]').first
            if not toggle_input.is_checked():
                toggle_input.click()
        except:
            pass
        
        # Phase 8: Paste code
        retry_action(
            lambda: click_in_builder(page, 'text=Custom HTML/JavaScript', builder_frame),
            action_name="Custom HTML element"
        )
        page.wait_for_timeout(1000)
        
        retry_action(
            lambda: find_element_with_fallback(page, SELECTORS["open_code_editor"]).click(),
            action_name="Open Code Editor"
        )
        page.wait_for_timeout(2000)
        
        code_editor = find_element_with_fallback(page, SELECTORS["code_editor_textarea"])
        code_editor.fill("")
        code_editor.fill(html_code)
        
        retry_action(
            lambda: find_element_with_fallback(page, SELECTORS["save_code_editor"]).click(),
            action_name="Save code"
        )
        page.wait_for_timeout(2000)
        
        # Phase 9: Save page
        retry_action(
            lambda: find_element_with_fallback(page, SELECTORS["save_page_button"]).click(),
            action_name="Save page"
        )
        page.wait_for_timeout(2000)
        
        # Phase 10: Screenshot verification
        retry_action(
            lambda: find_element_with_fallback(page, SELECTORS["preview_button"]).click(),
            action_name="Preview"
        )
        page.wait_for_timeout(3000)
        
        preview_page = page.context.pages[-1] if len(page.context.pages) > 1 else page
        preview_page.screenshot(path=f"preview_{step_name.replace(' ', '_')}.png", full_page=True)
        
        deployment_results[step_name] = "✅ SUCCESS"
        print(f"   ✅ {step_name} deployed and verified!")
        
        # Close preview tab if it's separate
        if len(page.context.pages) > 1:
            page.context.pages[-1].close()
        
    except Exception as e:
        deployment_results[step_name] = f"❌ FAILED: {str(e)[:100]}"
        print(f"   ❌ {step_name} deployment failed: {str(e)[:100]}")
        
        # Attempt recovery
        recovery_result = recovery_protocol(page, step_name, e)
        if recovery_result == "REAUTH":
            # Re-authenticate and continue
            pass
        elif recovery_result == "RESTART":
            # Navigate back and continue with next page
            continue

# Print deployment summary
print(f"\n{'='*60}")
print("📊 DEPLOYMENT SUMMARY")
print(f"{'='*60}")
for step_name, result in deployment_results.items():
    print(f"   {result} - {step_name}")

all_success = all("SUCCESS" in r for r in deployment_results.values())
if all_success:
    print(f"\n🎉 Full funnel deployed successfully!")
else:
    print(f"\n⚠️ Some pages had issues. Review results above.")

12. PUBLISHING (Only When User Approves)
⚠️ NEVER publish without explicit user approval.

WORKFLOW:
1. Build all pages
2. Save all pages
3. Preview all pages and verify rendering
4. Report to the user what was built
5. Provide preview screenshots for user review
6. WAIT for explicit user approval - do NOT proceed without it
7. ONLY THEN: Click "Publish" on each page

TO PUBLISH:
- Open each page in the builder
- Click the "Publish" button (top-right, next to the save icon)
- Confirm publication when prompted
- Repeat for each page in the funnel

# Publishing - Only after user approval

def publish_funnel(page, funnel_workspace_url, page_names):
    """
    Publish all funnel pages. ONLY call this after user has approved.
    """
    print("🚀 Publishing funnel pages...")
    
    for step_name in page_names:
        page.goto(funnel_workspace_url)
        page.wait_for_timeout(2000)
        
        # Click the step
        retry_action(
            lambda name=step_name: page.locator(f'text={name}').first.click(),
            action_name=f"Open step: {step_name}"
        )
        page.wait_for_timeout(2000)
        
        # Click Publish
        retry_action(
            lambda: find_element_with_fallback(page, SELECTORS["publish_button"]).click(),
            action_name=f"Publish: {step_name}"
        )
        page.wait_for_timeout(2000)
        
        # Handle confirmation dialog if one appears
        try:
            confirm_selectors = [
                'button:has-text("Confirm")',
                'button:has-text("Yes")',
                'button:has-text("Publish")',
                'button.btn-primary',
            ]
            confirm_btn = find_element_with_fallback(page, confirm_selectors, timeout=3000)
            confirm_btn.click()
            page.wait_for_timeout(1000)
        except:
            pass  # No confirmation dialog - publish was immediate
        
        print(f"   ✅ Published: {step_name}")
    
    print("🎉 All pages published!")

13. COMPLETE AUTOMATION SEQUENCE (Summary)
SETUP:
├── Configure browser with viewport 1440x900 minimum
├── Load or create persistent session
└── Handle 2FA if present (pause for manual intervention)

NAVIGATION:
├── Click Sites → Funnels (using fallback selectors)
└── Wait for funnel list to load (use safe_wait, not fixed timeout)

FUNNEL CREATION:
├── New Funnel → Blank → Name → Create
├── CAPTURE funnel workspace URL (critical for multi-page deployment)
└── Add steps for each page (name + path) → Create Funnel Step

FOR EACH PAGE:
├── Click step → Create from Blank → WAIT for builder to load
├── Acquire builder iframe context (get_builder_frame)
├── Close "Ask AI" popup (handle gracefully if absent)
├── Add Blank Section (inside builder frame)
├── Hover "+" → Add → Scroll down → Custom → Code (inside builder frame)
├── Click GREEN border (section) → Enable full width (section settings on main page)
├── Click BLUE "Custom HTML/JavaScript" → Open Code Editor (modal on main page)
├── Paste ENTIRE HTML code (try fill → JS eval → clipboard fallback)
│   └── OR paste iframe snippet if using iframe deployment method
├── Save code editor → Save page → Preview
├── Verify at 1440px, 768px, 375px (screenshots + horizontal scroll check)
├── Debug if needed → Re-save → Re-preview
│   └── If 3+ debug attempts fail → Switch to iframe method
└── Report results

MULTI-PAGE:
├── Loop through all funnel pages using captured workspace URL
├── Track deployment results per page
└── Generate deployment summary

REPORTING:
├── Tell user what was built
├── Provide preview screenshots
└── WAIT for explicit user approval

PUBLISHING:
├── ONLY when user approves
├── Publish each page → Confirm if prompted
└── Verify live URLs

HELPER FUNCTIONS REFERENCE (Complete)
All helper functions used throughout this guide, collected in one place for easy import:
import time
from playwright.sync_api import sync_playwright


def find_element_with_fallback(page_or_frame, selectors, timeout=5000, action="find"):
    """Try multiple selectors in order. Return first visible match."""
    errors = []
    for i, selector in enumerate(selectors):
        try:
            locator = page_or_frame.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout)
            if i > 0:
                print(f"   ℹ️ Used fallback selector #{i + 1}: {selector}")
            return locator
        except Exception as e:
            errors.append(f"  [{i + 1}] '{selector}': {str(e)[:80]}")
            continue
    raise Exception(f"All {len(selectors)} selectors failed:\n" + "\n".join(errors))


def retry_action(action_fn, max_retries=3, delay=2, action_name="action"):
    """Retry an action with delay between attempts."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            result = action_fn()
            if attempt > 1:
                print(f"   ✅ {action_name} succeeded on attempt {attempt}")
            return result
        except Exception as e:
            last_error = e
            print(f"   ⚠️ {action_name} - attempt {attempt}/{max_retries} failed")
            if attempt < max_retries:
                time.sleep(delay)
    raise Exception(f"❌ {action_name} failed after {max_retries} attempts: {last_error}")


def safe_wait(page, condition_fn, timeout=10000, poll_interval=500, description="condition"):
    """Wait for a condition to become true by polling."""
    start = time.time()
    while (time.time() - start) * 1000 < timeout:
        try:
            if condition_fn():
                return True
        except:
            pass
        time.sleep(poll_interval / 1000)
    print(f"⚠️ Timed out waiting for: {description}")
    return False


def get_builder_frame(page):
    """Locate and return the builder iframe context."""
    iframe_selectors = [
        'iframe[src*="builder"]',
        'iframe[src*="funnel"]',
        'iframe[id*="builder"]',
        'iframe[class*="builder"]',
        'iframe[title*="builder" i]',
    ]
    for selector in iframe_selectors:
        try:
            frame = page.frame_locator(selector).first
            frame.locator('body').wait_for(timeout=3000)
            return frame
        except:
            continue
    for frame in page.frames:
        if any(kw in (frame.url or "") for kw in ["builder", "funnel", "editor"]):
            return frame
    print("⚠️ No builder iframe detected - using main page.")
    return page


def click_in_builder(page, selector, builder_frame=None, timeout=5000):
    """Click an element inside the builder iframe with main-page fallback."""
    if builder_frame is None:
        builder_frame = get_builder_frame(page)
    try:
        if hasattr(builder_frame, 'locator'):
            builder_frame.locator(selector).click(timeout=timeout)
        else:
            builder_frame.locator(selector).click(timeout=timeout)
        return True
    except:
        try:
            page.locator(selector).click(timeout=timeout)
            return True
        except:
            return False


def handle_2fa_if_present(page):
    """Detect 2FA screen and pause for manual intervention."""
    indicators = [
        'input[name="code"]', 'input[name="otp"]',
        'input[placeholder*="verification" i]', 'input[placeholder*="code" i]',
        'text=Two-factor', 'text=Verify your identity',
    ]
    for selector in indicators:
        try:
            if page.locator(selector).is_visible(timeout=2000):
                print("🔐 2FA DETECTED - Complete verification in the browser window.")
                page.wait_for_url("**/dashboard**", timeout=300000)
                print("✅ 2FA completed.")
                return True
        except:
            continue
    if "dashboard" not in page.url:
        page.screenshot(path="login_failure.png")
        raise Exception("Login failed. Check credentials.")
    return False


def recovery_protocol(page, step_name, error):
    """Execute when all retries fail."""
    print(f"🚨 RECOVERY: {step_name} - {str(error)[:200]}")
    page.screenshot(path=f"recovery_{step_name.replace(' ', '_')}.png", full_page=True)
    if "login" in page.url:
        return "REAUTH"
    if "error" in page.url:
        page.goto("https://app.convertandflow.com/dashboard")
        return "RESTART"
    page.wait_for_timeout(5000)
    return "MANUAL"

14. UPDATING AN EXISTING PAGE (Not Just New Pages)

Sometimes you need to update a page that has ALREADY been deployed - not create a new one.

How to update an existing funnel page:
1. Navigate to Sites -> Funnels (or Websites)
2. Find the existing funnel in the list and click on it
3. Click on the specific step/page you want to update
4. The page builder will open with the EXISTING content already loaded
5. Click on the code element (the blue "Custom HTML/JavaScript" box)
6. Click "Open Code Editor"
7. You will see the current code - SELECT ALL and DELETE IT
8. Paste the NEW updated code
9. Click Save in the code editor
10. Click the Save button (floppy disk) in the top toolbar
11. Preview to verify the changes
12. Publish ONLY if user approves

Playwright code for updating an existing page:
def update_existing_page(page, funnel_name, step_name, new_html_code):
    # Navigate to Sites -> Funnels
    retry_action(
        lambda: find_element_with_fallback(page, SELECTORS["sidebar_sites"]).click(),
        action_name="Click Sites"
    )
    page.wait_for_timeout(1500)
    
    retry_action(
        lambda: find_element_with_fallback(page, SELECTORS["tab_funnels"]).click(),
        action_name="Click Funnels"
    )
    page.wait_for_timeout(1500)
    
    # Find and click the existing funnel
    retry_action(
        lambda: page.locator(f'text={funnel_name}').first.click(),
        action_name=f"Open funnel: {funnel_name}"
    )
    page.wait_for_timeout(2000)
    
    # Click the specific step
    retry_action(
        lambda: page.locator(f'text={step_name}').first.click(),
        action_name=f"Open step: {step_name}"
    )
    page.wait_for_timeout(3000)
    
    # Wait for builder to load
    builder_loaded = safe_wait(
        page,
        lambda: page.locator('iframe[src*="builder"]').count() > 0,
        timeout=15000,
        description="builder load"
    )
    builder_frame = get_builder_frame(page)
    
    # Click the existing code element
    retry_action(
        lambda: click_in_builder(page, 'text=Custom HTML/JavaScript', builder_frame),
        action_name="Click existing code element"
    )
    page.wait_for_timeout(1000)
    
    # Open code editor
    retry_action(
        lambda: find_element_with_fallback(page, SELECTORS["open_code_editor"]).click(),
        action_name="Open Code Editor"
    )
    page.wait_for_timeout(2000)
    
    # Replace the code
    code_editor = find_element_with_fallback(page, SELECTORS["code_editor_textarea"])
    code_editor.fill("")  # Clear existing
    code_editor.fill(new_html_code)  # Paste new
    
    # Save
    retry_action(
        lambda: find_element_with_fallback(page, SELECTORS["save_code_editor"]).click(),
        action_name="Save code"
    )
    page.wait_for_timeout(2000)
    
    retry_action(
        lambda: find_element_with_fallback(page, SELECTORS["save_page_button"]).click(),
        action_name="Save page"
    )
    page.wait_for_timeout(2000)
    
    print(f"Updated: {funnel_name} / {step_name}")

IMPORTANT: When updating, you do NOT need to create a new funnel or add new steps. You are editing the EXISTING code in the EXISTING page. Do not accidentally create a duplicate.


15. DEPLOYMENT REPORT TEMPLATE

After completing any deployment (new or update), send the user a report using this format:

DEPLOYMENT REPORT
Date: [date]
Account: [sub-account name]
Type: [New Funnel / Page Update / Multi-Page Funnel]

PAGES DEPLOYED:
| Page Name | URL Path | Status | Screenshot |
|-----------|----------|--------|------------|
| Landing Page | /landing | Deployed + Saved | preview_Landing_Page.png |
| Sales Page | /sales | Deployed + Saved | preview_Sales_Page.png |

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

Always include this report. Do not skip it. The user needs to know exactly what was done.


[ADD TO AGENTS.md]

## GHL/Convert and Flow Page Deployment
- Full instructions: ~/Downloads/[master-files-folder]/ghl-install-pages.md
- Use Playwright with launchPersistentContext (never launch())
- Always verify correct sub-account before building
- Default to Funnels unless user says Websites
- GHL credentials stored in ~/clawd/secrets/.env (GHL_EMAIL, GHL_PASSWORD)
- NEVER publish without explicit user approval
- ALWAYS send deployment report after completing


[ADD TO TOOLS.md]

## GHL Page Builder (Playwright Automation)
- Full guide: ~/Downloads/[master-files-folder]/ghl-install-pages.md
- Viewport minimum: 1440x900
- Builder loads inside nested iframes - use get_builder_frame() to switch context
- Every selector has fallback chains - use find_element_with_fallback()
- 2FA detection built in - pauses for manual intervention
- Two deployment methods: Direct code (default) and iframe (for complex/conflicting CSS)
- Credential location: ~/clawd/secrets/.env
- For updating existing pages: navigate to the funnel, open the step, replace the code in the code editor


[ADD TO MEMORY.md]

## GHL Page Deployment Skill Learned [DATE]
- Full guide saved to ~/Downloads/[master-files-folder]/ghl-install-pages.md
- Covers: new funnel creation, multi-page deployment, existing page updates, iframe method
- Sub-account switching, credential storage, deployment reporting all documented


This enhanced guide provides production-grade browser automation instructions for deploying SuperDesign exports into Convert & Flow / Go High Level. It includes iframe architecture handling, robust selector fallbacks, error recovery protocols, 2FA handling, viewport configuration, and an iframe deployment method for complex codebases. Follow each step precisely. When in doubt, wait longer rather than clicking too fast - the GHL builder needs time to load between actions.

