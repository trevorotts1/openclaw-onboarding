╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.

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
NOTE: TYP is recommended. If not yet installed, continue and revisit TYP
later if needed. You can still safely execute this skill without TYP - just
be mindful not to dump large blocks of content into core .md files. Add only
brief summaries and file path references to AGENTS.md, TOOLS.md, and MEMORY.md.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, always follow this skill's files. The skill takes precedence
over TYP on core file update decisions. TYP governs the storage method (lean
summaries + file paths). The skill governs the content and which files it
touches. When in doubt: skill docs win.


TYP FILE STORAGE INSTRUCTIONS (only read this if TYP confirmed)

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

RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT
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
Ask the operator. Do not guess. Do not assume.

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

# GHL Install Pages - Setup and Prerequisites

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


This guide covers everything the AI agent needs to have in place BEFORE deploying pages into GoHighLevel (Convert and Flow). This is about getting the tools ready. For the actual step-by-step deployment process, see INSTRUCTIONS.md.

This document assumes the HTML code is already written and ready to go. The agent is setting up the ability to insert that HTML code into GHL's page builder.


## What This Skill Does

This skill enables the AI agent to use browser automation to:
- Access a GoHighLevel / Convert and Flow account via a seeded Firebase refresh-token session (TOKEN-ONLY, D7) — NOT a login form
- Navigate to the page builder
- Create new funnels or website pages
- Paste HTML code into the builder's code block element
- Save, preview, and publish pages
- Update existing pages with new code

**Browser automation tier:** agent-browser (Vercel Labs, Skill 03) is PRIMARY; Playwright is the FALLBACK. Access is always established through the Firebase refresh-token seed path — the builder never renders a login form and never encounters a 2FA prompt under normal operation.


## Client Resource Matrix

Skill 6 does NOT require every host to match the operator's stack. The capability probe (Step 1) detects what the host actually has and selects the lane; the build quality follows the resources. Full lane detail and the capability-class table live in `ENV-MATRIX.md`.

| Client resource | Build quality | What to enable |
|---|---|---|
| agent-browser ≥ the Skill 03 pin (0.27.0) | Full (Lane 1, PRIMARY) | The default path — no other requirement; cross-origin iframe drag additionally needs the Playwright CDP hybrid |
| OpenClaw ≥ 2026.8.1 + browser plugin + Playwright | Full (alt-PRIMARY) | Prefer for iframe-heavy pages (frame-scoped `--frame` snapshots); an experimental upgrade — not yet wired as Skill 6 PRIMARY |
| OpenClaw ≥ 2026.8.1, no Playwright | Partial | ARIA/role snapshot inspection with limited act — pair with agent-browser |
| Pre-2.0 OpenClaw + agent-browser | Full (Lane 1) | No managed-browser features needed — an old OpenClaw does NOT block Skill 6 |
| CUA enabled | Optional last resort | Hard-UI / cross-origin pixel path ONLY. Do NOT document or require "everyone must install CUA" |
| No Firebase refresh token | Tier-2/Tier-3 auth only | Gated Tier-2 bootstrap only if policy allows; fail loud (Tier-3) when unattended |
| VPS headless | Per the ENV contract | Headless-only rules + durable-root paths: follow `ENV-MATRIX.md` |


## Prerequisites Verification

The agent must verify ALL of these are in place before proceeding:

1. [ ] Browser automation is available: agent-browser (Vercel Labs, Skill 03) PRIMARY; Playwright FALLBACK — at least one must be installed and working
2. [ ] A valid `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` exists in `~/.openclaw/secrets/.env` (TOKEN-ONLY, D7) — OR a persistent Playwright browser session exists at `~/.openclaw/playwright-data/ghl-install-pages` (Playwright fallback only)
3. [ ] Finished HTML code is ready to paste (all CSS must be inline or in style tags, no React, no external dependencies)
4. [ ] Page requirements are documented (page names, URL paths, which HTML code goes where)
5. [ ] GHL credentials are stored securely (see Step 6: Auth Ladder below)
6. [ ] Target SUB-ACCOUNT is identified (see Sub-Account Selection below)


## Step 1: Set Up the Browser Lane — agent-browser (PRIMARY) + Capability Probe

agent-browser (Vercel Labs) is the PRIMARY engine. It comes from Skill 03 (`03-agent-browser/` in this onboarding repo); **Skill 03 (Wave 1) must be complete BEFORE Skill 06 starts** — 06 is not parallel-safe with 03.

**1. Install / verify the agent-browser CLI.** Follow the 03-agent-browser skill, then verify the CLI resolves and matches the repo pin:

```bash
agent-browser --version
```

The version is **pinned to 0.27.0** — the single source of truth is `tools/gates.json` → `agent_browser_version_pin` (mirrored in `03-agent-browser/agent-browser-cli.pin`). The pin is enforced at runtime: `tools/browser_manager.py::assert_agent_browser_version()` fires at `browser_session()` entry, and `tools/inject-ghl-auth.sh` hard-fails with exit 70 on drift. A deliberate upgrade requires re-capturing the gates, then re-pinning via `GHL_AB_PINNED_VERSION`; `GHL_AB_ALLOW_VERSION_DRIFT=1` downgrades drift to a WARN — it is an operator acknowledgment, never a silent pass.

**2. Run the capability probe (MANDATORY — never skip).** The probe classifies which browser lanes this host actually has (agent-browser, OpenClaw managed browser, Playwright, CUA), which secrets resolve, and which lane to use:

```bash
bash tools/browser_manager.sh probe
# or
python3 tools/capability_probe.py
```

It writes `working/skill6-capability.json` (the run-evidence root, never inside the skill dir) with `selectedLane` and the fallback chain. **`selectedLane != null` is the Day-0 acceptance** — a host with zero browser lanes is not installable (fail closed). Do NOT require OpenClaw 2.0 or CUA for this install to pass when Lane 1 (agent-browser) works; a pre-2.0 OpenClaw host with agent-browser has full Skill 6 capability.

**3. Prove the lane through the gateway:**

```bash
bash tools/browser_manager.sh ensure
```

Expected output ends with: `ENSURED: session=... lock=held ttl=... — teardown trap installed.` NEVER invoke `agent-browser` directly and NEVER invent a per-iteration session name — every call routes through `tools/browser_manager.sh` (Step 7).


## Step 2: Playwright — FALLBACK-ONLY Lane (never Step 1)

Self-hosted Playwright is the FALLBACK engine for known-hard flows only (for example the cross-origin iframe drag). Install it **only when the capability probe says so** — i.e. `selectedLane` in `working/skill6-capability.json` names a Playwright-dependent lane, or a Playwright-hybrid flow (cross-origin drag/drop) is required on a standard-class host. **Playwright is never Step 1 and never the default engine.**

⚠️ **INTERPRETER TRAP (live 2026-07-08):** a bare `pip` or `playwright` on PATH
can belong to a DIFFERENT python than the `python3` that will run this skill's
tools (e.g. a Homebrew python3.14 without Playwright shadowing the interpreter
Playwright is installed under). Always install and verify **through the same
`python3` that will invoke the tools** (`python3 -m pip`, `python3 -m
playwright`) — never bare `pip`/`playwright`. The live build preflight
(F-P9 in `tools/ghl_form_builder.py`) hard-stops with the interpreter named if
Playwright is not importable under the running python, so an environment
mistake can never burn a live attempt.

On the fallback lane, execute the following commands to install Playwright:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

The first command installs the Playwright library for THIS `python3`. The second command downloads the Chromium browser that Playwright will control.

Verify installation — run with the SAME `python3` that will run the tools:
```bash
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright installed successfully')"
```

Expected output: "Playwright installed successfully" printed to stdout. If this
fails with `ModuleNotFoundError`, `which -a python3` shows the shadowing
install — re-run the two install commands with the intended interpreter's
absolute path.

**Fallback-lane launch configuration:**

# PERSISTENT SESSION - user logs in once, session saved automatically
# Session stored at: ~/.openclaw/playwright-data/ghl-install-pages/
# To reset and re-login: rm -rf ~/.openclaw/playwright-data/ghl-install-pages/

```python
import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=os.path.expanduser("~/.openclaw/playwright-data/ghl-install-pages"),
        headless=True,   # D6 HEADLESS-ONLY — never open a visible window (dev OR client). NEVER set False.
        viewport={"width": 1440, "height": 900},
        args=[
            "--window-size=1440,900",
            "--disable-blink-features=AutomationControlled",
        ]
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
```

Configuration notes:
- Always use launch_persistent_context (not regular launch). This saves login session so re-authentication is not required on every run.
- The user_data_dir ("./ghl_session") is where the browser saves cookies and session data. This folder persists between runs.
- headless MUST stay True (D6 HEADLESS-ONLY). A visible window is forbidden, dev OR client. Authentication on this lane is still the Step 6 auth ladder (token-only primary, gated Tier-2, fail-loud Tier-3) — the fallback lane changes the driver, never the auth doctrine.
- On the fallback lane only, an existing persistent session at `~/.openclaw/playwright-data/ghl-install-pages` may carry logged-in state while a token is unavailable — note it in MEMORY.md. Tier-1 token seeding remains the only unattended auth path.
- Below 1280px width: GHL's left sidebar collapses into a hamburger menu, breaking automation.
- Below 900px height: Modal dialogs may not fully render, cutting off buttons.


## Step 3: Browser Window Settings (every lane)

GHL's page builder requires specific minimum browser window size. If the window is too small, the sidebar collapses, buttons move around, and automation fails. These minimums apply to EVERY lane — the agent-browser gateway sessions and the Playwright fallback alike.

Required settings:
- Width: 1280 pixels (1440 recommended)
- Height: 800 pixels (900 recommended)

agent-browser sessions opened through `tools/browser_manager.sh` use 1440x900; the Playwright fallback sets `viewport` + `--window-size` in the Step 2 launch block.

- Below 1280px width: GHL's left sidebar collapses into a hamburger menu, breaking automation.
- Below 900px height: Modal dialogs may not fully render, cutting off buttons.


## Step 4: Identify and Switch to Correct Sub-Account

GHL/Convert and Flow uses a two-level structure:
- **Agency level:** The top-level dashboard where all clients are managed
- **Sub-account level:** Each client has their own sub-account with separate sites, funnels, and settings

The agent MUST be inside the correct sub-account before building pages. If pages are deployed in the wrong sub-account, the client will not see them.

To verify current sub-account:
1. Check the top-left corner of the GHL dashboard
2. The sub-account name is displayed next to the logo
3. If it shows the agency name (not the client's name), the agent is at agency level and must switch

To switch to the correct sub-account:
1. Click the sub-account name or dropdown in the top-left corner
2. Search for the client's sub-account name
3. Click to enter that sub-account
4. Verify the name in the top-left now matches the correct client

Always verify the correct sub-account is active before starting any page deployment.


## Step 5: Determine Deployment Target - Websites vs. Funnels

GHL has TWO places to build pages: Websites and Funnels. They use the exact same builder but serve different purposes.

**Use FUNNELS (default - use this 90% of the time):**
- Landing pages, opt-in pages, sales pages, checkout pages, thank you pages
- Any multi-step flow where a visitor moves through pages in order
- Most SuperDesign exports
- When target is not explicitly specified, default to Funnels

**Use WEBSITES (only when explicitly requested):**
- Standalone pages that are NOT part of a flow (like an About page or a blog)
- A full website with navigation between pages
- The user explicitly specifies "Website" not "Funnel"

If the user does not specify which one, default to Funnels.


## Step 6: Auth Ladder — TOKEN-ONLY (D7) Primary, Gated Tier-2, Fail-Loud Tier-3

> AUTH LADDER — 3 tiers, identical everywhere it is stated (Prerequisites
> auth bullet; Critical Things to Know; carried verbatim in INSTALL.md):
> Tier-1 TOKEN-ONLY (Firebase refresh) — the default, unattended path;
> Tier-2 gated email-2FA via tools/ghl_auth.py — ONLY when Tier-1 fails AND
> the policy gates allow; Tier-3 fail-loud — never a silent UI login.

**Tier-1 — TOKEN-ONLY (default, unattended).** The builder seeds the session from `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` (tools/seed-ghl-auth.py + tools/inject-ghl-auth.sh) and NEVER renders a login form and NEVER sees a 2FA prompt. If the token seed fails, the builder STOPS with a non-zero exit — it does NOT fall back to a login form.

**ALWAYS check for an existing token before prompting the user. Presence-only checks — NEVER print the token value:**

```bash
# Canonical secrets file (sole authoritative path — ~/clawd/secrets/.env is retired)
# Prints the COUNT of matching lines (1 = present, 0 = absent) — never the value
grep -c "^GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" ~/.openclaw/secrets/.env 2>/dev/null
# Live process env (token may already be exported) — count only, never the value
printenv | grep -c "^GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN="
```

**Tier-1 outcome:**
- Token found and non-empty: proceed (Step 3 window settings, then the build).
- Token missing/empty/revoked: Tier-1 fails → the operator must supply a fresh token (see token recovery below) and add it to `~/.openclaw/secrets/.env` before continuing.

**NEVER prompt for GHL_EMAIL or GHL_PASSWORD. Email/password login is not used by this skill.**

If the token needs to be added, store it in the canonical secrets file:
```bash
# Mac:
mkdir -p ~/.openclaw/secrets && nano ~/.openclaw/secrets/.env
```

Add the following line (replace with the actual token value):
```
GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=<your-token-here>
```

Save and close the file (Ctrl+O, Enter, Ctrl+X). Set permissions: `chmod 600 ~/.openclaw/secrets/.env`.

Load the token in automation scripts:
```python
import os
firebase_token = os.environ.get("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")
```

**Token recovery (fixes Tier-1):** re-grab a fresh token using the Convert and Flow Token Grabber Chrome extension (Skill 44 Action 5b), then update `~/.openclaw/secrets/.env` and re-run the seed.

**Tier-2 — GATED email-2FA bootstrap (only when Tier-1 fails AND policy allows).** The canonical auth entry point is the orchestrator `python3 tools/ghl_auth.py --session <sess> --out /tmp/<sess>/seed.json` (a 3-tier ladder). It always runs Tier 1 first; ONLY on token-absent/invalid does it evaluate the gated Tier-2 ladder, which requires ALL FOUR gates to pass — (A) recorded client authorization, (B) Gmail-access PROVEN by a live read BEFORE any login, (C) email is the selected 2FA method, (D) agency creds in the client store. It is bounded (<=3 attempts, backoff, hard-stop on lockout/captcha) and on success SELF-HEALS a fresh `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` to the client store so the next run is Tier 1 again. Preview the tier without logging in: `python3 tools/ghl_auth.py --session <sess> --out <path> --check`.

**Tier-3 — fail loud.** Any gate fail, lockout, captcha, or an unattended run with no valid token exits non-zero with a precise client instruction. A genuinely-blocked two-factor PAUSES + screenshots + surfaces to the operator instead of waiting silently. **A silent UI login is NEVER the happy path** — the builder MUST NOT auto-open the Sign-in form or a two-factor prompt.


## Step 7: Route Every Call Through the Gateway — Frame-Scoped Entry Points

The agent does NOT hand-roll a helper table. The legacy Playwright-era helper list in `ghl-install-pages-full.md` is **HISTORICAL (v2.0)** — that file is archive-only and must NOT be followed for new installs (it is superseded by `ghl-browser-builder-full.md` v3.0). The current entry points are:

1. **Singleton gateway — `tools/browser_manager.sh`.** Route EVERY agent-browser call through it:
   1. `bash tools/browser_manager.sh ensure` — circuit-breaker check → box-wide lock (flock if present, else atomic-mkdir) → lease → TTL self-kill timer → open the ONE canonical session → install `trap _bm_teardown EXIT`.
   2. `bash tools/browser_manager.sh eval|open|snapshot|wait|find|fill -- <args>` — thin lock-asserting pass-throughs (force `--headed false`, per-call timeout).
   3. `bash tools/browser_manager.sh run-detached -- <build-cmd>` — detach safely (the subtree owns lock+lease+TTL+trap, so detach-and-exit can never orphan).
   4. `SESSION="$(bash tools/browser_manager.sh session-name)"` or `python3 tools/ghl_builder.py browser-session` — print the canonical name (`ghl-skill6-<location-id>`).
   NEVER invoke `agent-browser` directly and NEVER invent a per-iteration session name.

2. **Nested + cross-origin iframes.** The builder loads inside nested iframes. agent-browser inlines iframe accessibility into the top snapshot and switches frames with `frame @ref` / `frame main` (gate #12). For cross-origin in-frame drag, click, or edit actions, call the frame-scoped entrypoints in `tools/ghl_iframe_drag.py` — `drive_drag(...)`, `drive_frame_click(...)`, `smoke_first(...)` (Playwright over the agent-browser CDP; the `IFRAME_SELECTORS` constant holds the form/survey/page_code presets). Missing Playwright fails CLOSED: `IframeDragError("playwright-unavailable")`, exit 2 — never a fake pass. The agent-browser ladder `tools/ghl_iframe_dragdrop.py` (text-drag → in-frame JS → detect-JS) runs first for same-origin surfaces.

3. **Recovery = the gateway contract itself.** The circuit-breaker PARKS a flaky build and reports loudly (via Rescue Rangers); the hourly reaper `scripts/agent-browser-reaper.sh` (13 * * * *) is the backstop for a hard crash; the guaranteed teardown trap closes the session. A failed action is surfaced, never papered over.


## Step 8: Update Core .md Files

Follow TYP rules — only add summaries and file path references. The stamp text is FIXED: copy the blocks from `CORE_UPDATES.md` **EXACTLY** — an edited doctrine sentinel fails the doctrine checks. These three sentinels MUST appear verbatim in AGENTS.md + TOOLS.md:

```
GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA
GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY
SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop
```

**Add to AGENTS.md** — copy the block `## GHL Page Deployment [PRIORITY: HIGH]` EXACTLY from CORE_UPDATES.md ("AGENTS.md - UPDATE REQUIRED"). It carries, verbatim:
- Full guide: `[MASTER_FILES_FOLDER]/OpenClaw Onboarding/06-ghl-install-pages/ghl-browser-builder-full.md`
- The engine line: agent-browser (PRIMARY, headless, isolated `--session <client>`); Playwright is FALLBACK only and uses launchPersistentContext (NEVER launch())
- The SINGLETON POOLED BROWSER gateway paragraph (tools/browser_manager.sh owns the ONE session `ghl-skill6-<location-id>`, the box-wide lock, lease, TTL, circuit-breaker, teardown trap; reaper cron `13 * * * *`)
- The TOKEN-ONLY (D7) doctrine block + HARD RULE (never ask for/type/fall back to login/email/password/2FA; token failure = STOP and report; re-grab via the Token Grabber)
- The TIER-2 EMAIL-2FA FALLBACK block (gated A/B/C/D, bounded, self-heals to TOKEN-ONLY; all login/2FA code in tools/ghl_auth_fallback.py + tools/ghl_login_browser.py; CI guard scripts/guard-ghl-auth-fallback.sh)
- Always verify the correct sub-account before building (refuse on mismatch)
- Credentials: `~/.openclaw/secrets/.env` — `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` (canonical; CLIENT key only). Never the operator's keys on a client box.
- Surveys + Forms are the SAME ONE GHL rail

**Add to TOOLS.md** — copy the block `## GHL Page Builder (Browser Automation)` EXACTLY from CORE_UPDATES.md ("TOOLS.md - UPDATE REQUIRED"). It carries, verbatim:
- The same full-guide path and engine line, the three doctrine sentinels, and the gateway 4 steps (`ensure` → `eval|open|snapshot|wait|find|fill` → `run-detached` → `session-name`)
- The exit-75 refusal outside a `browser_session()` bracket; ADVISORY openclaw.json config vs the REAL cap env vars (AB_MAX_SESSIONS, AB_SESSION_TTL, AB_CALL_TIMEOUT, AB_BREAKER_MAX, AB_MAX_LIVE, AB_HARD_AGE_MIN, AB_PROC_HARD_AGE_MIN); the reaper contract
- The token-seed how-to (seed-ghl-auth.py → inject-ghl-auth.sh; env order GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN → CAF_FIREBASE_REFRESH_TOKEN → GHL_FIREBASE_REFRESH_TOKEN; exit 2 = no token, exit 3 = revoked) + the TIER-2 entry `python3 tools/ghl_auth.py`
- Viewport minimum 1440x900; frame-scoped iframe handling (agent-browser `frame @ref` / `frame main`; cross-origin drag/click/edit via tools/ghl_iframe_drag.py behind the gateway)
- `zhc` prefix on every name; marker-string verification of every save/preview/publish; NEVER publish without explicit approval; deployment report after every deployment; the survey/form rail

**Add to MEMORY.md** — copy the block `## GHL Page Deployment Skill - Installed [DATE]` EXACTLY from CORE_UPDATES.md ("MEMORY.md - UPDATE REQUIRED"): the TOKEN-ONLY summary + the coverage line, plus the full-guide reference.

Apply the sentinel comment once the blocks are in: `<!-- skill:06-ghl-install-pages:core-update-applied -->`

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

**During this installation, you may encounter instructions to restart the OpenClaw gateway.**

**YOU ARE FORBIDDEN from triggering gateway restarts yourself.**

### Correct Process
When a gateway restart is needed:
1. **STOP** - Do NOT execute the restart command
2. **NOTIFY** the user: "This installation requires an OpenClaw gateway restart to complete."
3. **INSTRUCT**: "Type `/restart` in Telegram to trigger it"
4. **WAIT** for user action - do NOT proceed until confirmed

### Forbidden Actions
- Do NOT run `openclaw gateway restart` without explicit user permission
- Do NOT say "I will restart the gateway now" without asking first
- Do NOT assume the user wants the restart

---
