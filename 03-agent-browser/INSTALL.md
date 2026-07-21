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
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

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
   - OpenClaw Master Files Starter
   - openclaw-master-files
   - Any variation of "openclaw" + "master" or "files" or "documents"
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

---

# INSTALL.md - Agent Browser (Vercel)

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


## Goal

Ensure `agent-browser` is installed and available as the primary browser automation tool.

## Step 1 - Check if agent-browser is installed

Run:
```bash
command -v agent-browser >/dev/null 2>&1 && echo "agent-browser: installed" || echo "agent-browser: NOT INSTALLED"
```

## Step 2 - Install agent-browser (only if missing)

**INSTALL THE PIN, NEVER A BARE `npm install -g agent-browser`.** This skill
records a known-good, proven CLI version in `agent-browser-cli.pin` (see
`CLI-VERSION-PIN.md` for why, and for the bump procedure). A bare install
resolves to whatever the registry currently calls latest, so on any day the
registry default is not the pinned release, a fresh install silently places an
UNPROVEN release on the box — and `qc-agent-browser.sh` then hard-FAILS that box
for a version mismatch it was the install that introduced.

Read the pin and install exactly that version:
```bash
AB_SKILL_DIR="$HOME/.openclaw/skills/03-agent-browser"
[ -d "/data/.openclaw/skills/03-agent-browser" ] && AB_SKILL_DIR="/data/.openclaw/skills/03-agent-browser"
AB_PIN="$(tr -d '[:space:]' < "$AB_SKILL_DIR/agent-browser-cli.pin")"
[ -n "$AB_PIN" ] || { echo "REFUSING: agent-browser-cli.pin is missing or empty at $AB_SKILL_DIR"; exit 1; }
echo "Installing pinned agent-browser version: $AB_PIN"
npm install -g "agent-browser@$AB_PIN"
agent-browser install
```

If the pin file cannot be read, STOP and report it. Do not fall back to an
unpinned install — an unproven CLI is the defect this pin exists to prevent.

**If the above fails with a permissions error**, try (still pinned):
```bash
sudo npm install -g "agent-browser@$AB_PIN"
```

If `sudo` is not available or still fails, tell the user:
"The agent-browser install requires npm global permissions. Please ask your system admin or run the terminal as Administrator (Windows) or with sudo (Mac/Linux)."

Do NOT proceed to Step 3 until `npm install -g "agent-browser@$AB_PIN"` completes without error.

## Step 3 - Verify agent-browser works

Run:
```bash
agent-browser --help | head -20
```

### Step 3b - Verify the INSTALLED version equals the pin

Help output and reference tokens do not tell you WHICH version is installed.
Compare it to the pin explicitly:
```bash
AB_INSTALLED="$(agent-browser --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
if [ "$AB_INSTALLED" = "$AB_PIN" ]; then
  echo "OK — installed agent-browser $AB_INSTALLED matches the pin"
else
  echo "MISMATCH — installed '$AB_INSTALLED', pinned '$AB_PIN'"
fi
```

On MISMATCH, do NOT proceed and do NOT re-pin to whatever is installed. Either
re-run Step 2 to land the pinned version, or — if the newer release is genuinely
wanted — prove it on the operator's own box first and bump the pin through
`scripts/bump-agent-browser-cli-pin.sh <new-version> "<reason>"`, which updates
`agent-browser-cli.pin` and `CLI-VERSION-PIN.md` together. `qc-agent-browser.sh`
asserts this same comparison, so a mismatch left here fails QC later anyway.

## Step 4 - Smoke test a simple browser session

Run (HEADLESS — `--headed false` is mandatory; a visible browser window must NEVER
open on a client box, even for a smoke test).

**GUARANTEED-CLOSE (AUD-21 / FLEET-FIX Area 2 / B.3):** run the three
commands as ONE subshell with a `trap ... EXIT` around `close`, not as three
independent commands. If `open` or `snapshot` throws (a bad URL, a dead CDP
socket, a killed process), a plain three-line sequence would skip `close` and
leak the session — the exact `~/.agent-browser/*.engine` orphan class this
skill's own "Lifecycle hygiene" section (below) warns about. The trap makes
`close` run unconditionally, every time, while still surfacing the real
open/snapshot exit code (not swallowed by `close`'s own exit code):
```bash
(
  set +e
  trap 'agent-browser close' EXIT
  agent-browser --headed false open https://example.com
  agent-browser snapshot -i
)
```

If the snapshot shows interactive elements with refs like `@e1`, `@e2`, installation is good.
If the subshell exits non-zero, `close` still ran (check `agent-browser state clean --older-than 1`
if you suspect a leaked descriptor anyway) — investigate the open/snapshot failure per the reason above.

## Notes

- This tool is the preferred option for web automation steps in later skills.
- If agent-browser is unavailable for any reason, later skills may fall back to Playwright with persistent context.

## Lifecycle hygiene (orphan prevention)

agent-browser keeps per-session engine descriptors under `~/.agent-browser/*.engine`
and exposes maintenance verbs:

```bash
agent-browser doctor --fix            # auto-cleans stale socket/pid/version sidecars (--fix gates destructive purges)
agent-browser state clean --older-than 1   # reap dead session state older than N days
agent-browser close --all             # close every live session (blast-radius: only for a reaper / breaker trip)
```

A build that crashes before teardown leaks an `.engine` descriptor (and possibly
a Chromium). Skill 06 prevents this two ways:

- **Gateway:** every agent-browser call in Skill 06 routes through
  `06-ghl-install-pages/tools/browser_manager.sh` (ONE canonical session, box-wide
  lock, TTL, and a guaranteed `trap _bm_teardown EXIT` that runs `close` +
  `state clean`/`state clear`).
- **Host reaper backstop:** `scripts/agent-browser-reaper.sh` runs every 10
  minutes (wired by `ensure-pipeline-crons.sh`): closes expired-lease sessions,
  runs `doctor --fix` + `state clean --older-than`, sweeps dead descriptors, and
  tripwires Chromium UNDER the agent-browser / Playwright profile tree ONLY
  (never a bare `chrome`/`Chrome`/`Claude` process). Runs as the box user, never
  root. **SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed
  teardown, reaper backstop.**

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
