> **N24 - Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.

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
Proceed to the instructions below.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Tell the user you must be taught the
Teach Yourself Protocol first.

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, always follow this skill's files. The skill takes precedence
over TYP on core file update decisions. TYP governs the storage method (lean
summaries + file paths). The skill governs the content and which files it
touches. When in doubt: skill docs win.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START


RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING.
RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT. Execute steps exactly as written.
RULE 3: NEVER MODIFY API keys, commands, config values, model names, or file
        paths without permission. Model name spelling matters.
RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING.
RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE.
RULE 6: REPORT WHAT YOU DID.

==================================================================
LOCAL EMBEDDER (SKILL 76) - INSTALLATION GUIDE
==================================================================

Client Macs only (Apple Silicon, macOS 14 or newer). On a VPS, a Contabo box
or inside Docker the installer prints "SKIPPED" and exits 0.

The fleet roll runs this for you: update-skills.sh calls `wire.sh --idempotent`
once per onboarding version and retries on the next roll when it exits 1. Run
it by hand only when the operator asks.

STEP 1: PREVIEW (reads only, changes nothing)

   bash wire.sh --dry-run

STEP 2: INSTALL

   bash wire.sh

It reuses a running Ollama 0.36.0 or newer untouched, upgrades an older one in
place only when it is idle, or installs the headless Ollama CLI under
~/.openclaw/ollama/ (LaunchAgent com.blackceo.ollama-serve). Then it pulls
embeddinggemma-2:740m, pins num_ctx 8192 on that same tag, switches
memory.search to it and re-indexes each agent once.

STEP 3: OPTIONAL, OPERATOR ONLY

   bash wire.sh --with-ornith

Also pulls ornith-1.5:9b and pins it (num_ctx 32768) on its own tag. It writes
no chat-model config; adding ornith to OpenClaw is a separate manual step the
operator approves.

STEP 4: VERIFY

   python3 ~/.openclaw/skills/shared-utils/embedding_health.py --json

Index 1 must pass leg-a with "local Ollama". No model is loaded by the check.

NEVER: run Ollama's install.sh, set OLLAMA_CONTEXT_LENGTH, touch
~/.ollama/id_ed25519*, run `ollama signout`, or edit models.providers.
