
╔══════════════════════════════════════════════════════════════╗
  MANDATORY TSP CHECK - READ THIS BEFORE ANYTHING ELSE
DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TSP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TSP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TSP"
- Look in your session context for prior TSP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TSP:
Proceed to the instructions below. Follow the TSP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TSP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TSP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TSP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TSP CONFIRMED.

TSP FILE STORAGE INSTRUCTIONS (only read this if TSP confirmed)

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


# SuperDesign - Installation and Setup Guide

This guide walks you through everything you need to install and configure before you can start using SuperDesign to create website designs. Follow every step in order. Do not skip anything.


## What Is SuperDesign?

SuperDesign is an AI-powered design tool that helps you create website designs using plain English. You describe what you want, and it creates visual layouts along with the actual code to build them.

Think of it like an architect who draws up blueprints AND gives you a construction-ready framework. You still need to add your own words, images, and branding, but the structure is done for you.

SuperDesign has three ways to use it:
- The Web App (a website you visit in your browser)
- The CLI (commands you type in your computer's terminal)
- The IDE Extension (a plugin for code editors like VS Code or Cursor)

This installation guide covers setting up all three options. You only need the ones that apply to you.


## Prerequisites - What You Need Before Starting

Before you install anything, make sure you have these items ready:

1. A computer running Mac, Windows, or Linux.

2. Google Chrome browser installed. You need Chrome specifically because the SuperDesign Chrome Extension only works in Chrome. You can download Chrome at https://www.google.com/chrome if you do not already have it.

3. Node.js version 16 or higher installed on your computer. Node.js is a program that lets you run JavaScript tools on your computer. To check if you have it, open your terminal (on Mac, search for "Terminal" in Spotlight) and type:

   node --version

   If you see a number like v18.0.0 or higher, you are good. If you see "command not found" or a number below v16, you need to install it:

   - On Mac (using Homebrew): Open Terminal and type: brew install node
   - On Mac (without Homebrew): Go to https://nodejs.org and download the LTS version. Open the downloaded file and follow the installer prompts.
   - On Windows: Go to https://nodejs.org and download the LTS version. Run the installer.
   - On Linux (Ubuntu/Debian): Open Terminal and type: sudo apt update && sudo apt install nodejs npm

4. npm (Node Package Manager). This comes automatically when you install Node.js. Verify by typing npm --version in your terminal.


## Part 1: Install the SuperDesign Skill for OpenClaw

This step connects SuperDesign to your OpenClaw agent so it knows how to use the tool.

1. Open your terminal.

2. Type this command and press Enter:

   npx clawhub install superdesign

3. Wait for the installation to finish. You will see a success message when it completes.

4. Verify the skill files were installed by typing:

   ls ~/.agents/skills/superdesign/

5. You should see files including SKILL.md, INIT.md, and SUPERDESIGN.md. If you see these files, the skill is installed correctly.


## Part 2: Install the SuperDesign CLI (Command Line Tool)

The CLI lets you run SuperDesign commands directly from your terminal without opening a browser.

1. Open your terminal.

2. Type this command and press Enter:

   npm install -g @superdesign/cli@latest

   If you get a "permission denied" error on Mac or Linux, try this instead:

   sudo npm install -g @superdesign/cli@latest

   You may be asked for your computer password. Type it in (you will not see the characters as you type - that is normal) and press Enter.

3. Verify the CLI installed correctly by typing:

   superdesign --version

4. You should see a version number. If you see "command not found" instead, the installation did not work. Try running the install command again, or use npx superdesign instead of superdesign for all future commands.

5. Log in to your SuperDesign account by typing:

   superdesign login

6. A browser window will open. Complete the login process in the browser. Do not continue to the next step until you see a success message.

7. Verify your login worked by typing:

   superdesign --help

8. You should see a help menu listing all available commands with no error messages about authentication.


## Part 3: Install the Chrome Extension (For Website Cloning)

The Chrome Extension lets you capture (clone) any live website and bring it into SuperDesign as an editable starting point. This is one of the most powerful features, and it only works in Google Chrome.

1. Open Google Chrome.

2. Go to the Chrome Web Store by typing this in your address bar: https://chromewebstore.google.com

3. In the search box at the top, type "Superdesign" and press Enter.

4. Look for the SuperDesign extension in the results. Click on it.

5. Click the blue "Add to Chrome" button.

6. A popup will appear asking you to confirm. Click "Add extension."

7. Look for the SuperDesign icon in your browser toolbar (the area at the top right of Chrome where small icons appear).

8. If you do not see the icon, click the puzzle piece icon in your toolbar (this is the Extensions menu). Find SuperDesign in the dropdown list and click the pin icon next to it. This pins the SuperDesign icon to your toolbar so it is always visible.

9. The Chrome Extension is now installed and ready to use.


## Part 4: Set Up the Web App Account

The Web App is the browser-based version of SuperDesign where you can see designs on a visual canvas.

1. Open your browser and go to https://app.superdesign.dev

2. If this is your first time, you will see a login or signup screen. Create an account using Google OAuth or your email address.

3. Once logged in, you will see the main workspace. This is the canvas area where your designs will appear, and a chat panel where you type design instructions.

4. You are now set up to use the Web App.

Important note about credits: The Web App gives you a limited number of free design credits per week. When you run out, you will need to wait for them to reset or upgrade to a Pro plan. The CLI and IDE Extension can use your own AI API key for unlimited generation (see Part 6 below).


## Part 5: Install the Skill Repository (For AI Agent Integration)

This step gives your AI coding agent (like Cursor, Claude Code, or OpenClaw) access to SuperDesign's full command library and standard operating procedures.

1. Open your terminal.

2. Type this command and press Enter:

   npx skills add superdesigndev/superdesign-skill

3. Wait for the download to complete.

4. This installs the skill files including CLI command definitions, standard operating procedures, agent rules, and the /superdesign slash command.


## Part 6: Set Up the IDE Extension (Optional - For Code Editor Users)

If you use a code editor like VS Code, Cursor, or Windsurf, you can install the SuperDesign extension directly inside it. This gives you unlimited design generation using your own AI API key instead of SuperDesign's limited free credits.

### Step 6A: Install the Extension

1. Open your code editor (VS Code, Cursor, or Windsurf).

2. Press Cmd+Shift+X on Mac (or Ctrl+Shift+X on Windows/Linux) to open the Extensions panel.

3. In the search box, type "SuperDesign."

4. Look for the extension published by "SuperdesignDev" (this is the official one). There may be an older version by "iganbold" - do not install that one.

5. Click the "Install" button.

### Step 6B: Configure Your AI API Key

This is the step that gives you unlimited design generation. You are telling SuperDesign to use YOUR AI account instead of their limited credits.

1. Press Cmd+Shift+P on Mac (or Ctrl+Shift+P on Windows/Linux) to open the Command Palette.

2. Type: superdesign: configureApiKey

3. Select it and enter your API key. You can use:
   - An Anthropic API key (recommended - Claude models work best)
   - An OpenAI API key
   - An OpenRouter API key

4. To set which AI provider to use, open the Command Palette again (Cmd+Shift+P) and type: superdesign: openSettings

5. Find the "AI Model Provider" setting and set it to "anthropic" (or "openai" or "openrouter" depending on which key you provided).

### Step 6C: Initialize Your Project

1. Open your project folder in the code editor (or create a new empty folder).

2. Open the Command Palette (Cmd+Shift+P).

3. Type: superdesign: initializeProject

4. Press Enter. This creates a .superdesign/ folder in your project with all the configuration files SuperDesign needs.

5. Verify it worked by checking that these files were created:
   - .superdesign/ folder (the main working directory)
   - CLAUDE.md file (design rules for Claude Code)
   - If using Cursor: .cursor/rules/design.mdc file
   - If using Windsurf: .windsurfrules file


## Part 7: Create Your First Test Project

This step confirms everything is working correctly.

1. Open your terminal.

2. Type this command and press Enter:

   superdesign create-project --title "MY TEST Page" --json

3. You should get a response that includes a Project ID and a Draft ID. Save both of these somewhere safe - you will need them for design commands later.

4. If you got an error, go back through the installation steps and check that each one completed successfully. The most common issues are:
   - Not logged in (run superdesign login again)
   - CLI not installed (run the npm install command from Part 2 again)
   - Node.js not installed or too old (check with node --version)

5. Test the inspiration search by typing:

   superdesign search-prompts --keyword "landing page" --json

6. You should see JSON results with design prompt suggestions. If you see results, the CLI is fully working.


## Part 8: Save the Full Documentation

Following the TSP (Teach Yourself Protocol), save the complete SuperDesign guide to your master files folder:

1. The full documentation should be saved to:
   ~/Downloads/openclaw-master-files/superdesign/superdesign-instructions.md

2. Add a brief summary to your AGENTS.md file (do not paste the full document):

   ## SuperDesign Web Design Skill [PRIORITY: HIGH]
   SuperDesign (superdesign.dev) is an AI-powered design agent for creating website designs.
   Three modes: Web App (browser, Chrome extension cloning), CLI (terminal commands), IDE Extension.
   Exports: React code, HTML/CSS, style.md (design system document).
   Deep file: ~/Downloads/openclaw-master-files/superdesign/superdesign-instructions.md

3. Add a brief summary to your TOOLS.md file:

   ## SuperDesign [PRIORITY: HIGH]
   Design agent for websites and UI. Three modes: Web App, CLI, IDE Extension.
   CLI install: npm install -g @superdesign/cli@latest
   Skill install: npx clawhub install superdesign
   Key commands: superdesign create-project, superdesign iterate-design-draft, superdesign extract-brand-guide
   Deep file: ~/Downloads/openclaw-master-files/superdesign/superdesign-instructions.md


## Installation Complete - What is Next?

You now have SuperDesign fully installed and configured. Here is what you have set up:

- The OpenClaw skill (so your AI agent knows about SuperDesign)
- The CLI tool (so you can run design commands from the terminal)
- The Chrome Extension (so you can clone live websites)
- The Web App account (so you can use the visual canvas)
- The Skill Repository (so AI agents have full access to SuperDesign commands)
- The IDE Extension (optional - for unlimited generation in your code editor)

To learn how to actually use SuperDesign day to day, see the INSTRUCTIONS.md file.
To see real examples of SuperDesign in action, see the EXAMPLES.md file.
For the complete unabridged reference, see the superdesign-full.md file.
