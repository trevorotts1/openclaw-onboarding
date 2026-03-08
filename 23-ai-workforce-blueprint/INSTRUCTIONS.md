# AI Workforce Blueprint - Build Instructions

## The 3 Options

### Option C - Audit / Resume Mode (Default for returning users)
**This is the default.** If you already have a workforce folder, run this every time.

**Say this:** "Audit my AI workforce." or just run the script again.

**What the script does automatically:**
1. Scans for an existing workforce folder
2. If found, asks: "Run in audit mode? (Y/n)" - default is YES
3. Scans every dept folder for missing files
4. Adds anything missing: good-examples.md, bad-examples.md, tools.md
5. Checks if Coaching Personas are installed - if yes, adds `governing-personas.md` to each dept and updates every `00-START-HERE.md` with a Governing Personas section
6. Never overwrites or deletes anything that already exists

**Use this when:**
- You installed skill 21 (personas) after already building your workforce
- You added new departments and need them audited
- You want to make sure nothing is missing
- Any time you re-run the script

---

### Option A - Full Automated Build (For brand-new workforces)
Your AI asks you questions and builds everything automatically.

**Say this:** "Build my AI workforce. Use Option A."

**What happens:**
1. AI asks: What is the name of your business?
2. AI asks: What are your departments? (Use the starter list in the blueprint if unsure)
3. AI asks: What roles exist in each department?
4. AI asks: What are the top 3-7 tasks each role performs?
5. AI asks: What tools does each role use?
6. AI creates all folders, Start Here files, routing file, and starter SOPs
7. AI shows you the complete folder tree when done

### Option B - Manual Build
You build everything yourself using the blueprint as your guide.
Read `ai-workforce-blueprint-full.md` from start to finish.

### Option C - Resume / Audit Mode
For businesses that already started a structure.

**Say this:** "Audit my AI workforce at [folder path]."

**What happens:**
- AI scans existing folders
- Reports what exists, what is missing, what is incomplete
- Fills gaps: missing Start Here files, missing routing logic, missing role files
- Does NOT delete or overwrite anything you already have

---

## The Required Files in Every Role Folder

Every role folder MUST have these files. No exceptions.

| File | What it is |
|------|-----------|
| `00-START-HERE.md` | First file the AI reads. What this role does, who owns it, what tools it uses, where to find files |
| `01-[task-name].md` | How-to file for task 1. Numbered, sequential |
| `02-[task-name].md` | How-to file for task 2 |
| (continue numbering) | One file per major task |
| `good-examples.md` | Examples of excellent output for this role |
| `bad-examples.md` | Examples of bad output - what to avoid |
| `tools.md` | List of every tool this role uses with login locations and instructions |

## The Routing File (Universal SOPs)

Every workforce structure needs one routing file at the top level:
`universal-sops/00-ROUTING.md`

This file tells the AI:
- Which department owns each type of task
- Which role inside that department handles it
- Which specific file in that role folder to read first

Without a routing file, the AI guesses. With a routing file, the AI always goes to the right place.

## Naming Convention (Non-Negotiable)

- Department folders: `[name]-dept/` (e.g., `sales-dept/`, `marketing-dept/`)
- Role folders: descriptive lowercase with hyphens (e.g., `lead-generation/`, `content-writer/`)
- Files: numbered with two digits (e.g., `01-`, `02-`) so they sort correctly
- No spaces in folder or file names. Ever.

## Signs Your Structure Is Working

- Your AI routes tasks to the right department without being told
- Output is consistent - same quality every time
- You can walk away and the AI keeps working
- Adding a new task means adding one .md file, not re-explaining everything
- New team members (human or AI) can onboard themselves by reading the folders
