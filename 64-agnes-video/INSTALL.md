> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.

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

IF YOU HAVE BEEN TAUGHT TYP:
Proceed. Follow the TYP file storage structure — save the full reference
(`agnes-video-full.md`) to the master files folder and keep only a lean pointer
in your core .md files.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Tell the user you have not been taught the Teach Yourself
Protocol yet and cannot safely learn these instructions until you have.

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If this skill's files conflict with TYP regarding WHICH core .md files to update
or WHAT content to add, always follow this skill's files. TYP governs the storage
method (lean summaries + file paths). The skill governs the content. Skill docs win.

══════════════════════════════════════════════════════════════════

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING. Read this entire document and
        SKILL.md, agnes-video-full.md, CORE_UPDATES.md, and QC.md first.
RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT. Execute steps exactly as written.
RULE 3: NEVER MODIFY MODEL NAMES, ENDPOINTS, OR THE CREDENTIAL NAME. Copy them
        character for character. NEVER print the credential value.
RULE 4: BUILD A CHECKLIST BEFORE EXECUTING, and confirm it with the user.
RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE.
RULE 6: REPORT WHAT YOU DID.

══════════════════════════════════════════════════════════════════
AGNES VIDEO V2.0 — INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

This is a REFERENCE skill. It does NOT create an Agnes account or write a new
credential. The `AGNES_AI_API_KEY` is ALREADY provisioned fleet-wide (the same
key that backs the registered `agnes/agnes-2.0-flash` model, endpoint
`apihub.agnes-ai.com/v1`). Installation = confirm the reference is present, the
existing key is visible, the endpoint responds, and the core files carry a lean
pointer.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CONFIRM THE SKILL FILES ARE PRESENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Confirm this folder contains: SKILL.md, INSTRUCTIONS.md, EXAMPLES.md,
   INSTALL.md, CORE_UPDATES.md, QC.md, agnes-video-full.md, and
   qc-agnes-video.sh.

2. Read agnes-video-full.md end to end. That is the exhaustive reference.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: CONFIRM THE CREDENTIAL IS SET (SET / NOT-SET ONLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

3. Confirm `AGNES_AI_API_KEY` is present WITHOUT printing its value:

     openclaw config get AGNES_AI_API_KEY >/dev/null 2>&1 && echo "SET" || echo "NOT-SET"

   Or check that the env var is non-empty without echoing it:

     [ -n "$AGNES_AI_API_KEY" ] && echo "SET" || echo "NOT-SET"

4. If NOT-SET: the key is normally already on the box as fleet infrastructure.
   Do NOT invent, substitute, or paste a key. Report NOT-SET to the operator and
   stop — this is an infrastructure gap, not something this skill provisions.

   NEVER echo, cat, or log the key value. SET / NOT-SET only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: SELF-TEST (OPTIONAL — COSTS ~ $0 CURRENTLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

5. Create a tiny task (shortest valid clip, num_frames 81):

     curl -s -X POST https://apihub.agnes-ai.com/v1/videos \
       -H "Authorization: Bearer $AGNES_AI_API_KEY" \
       -H "Content-Type: application/json" \
       -d '{"model":"agnes-video-v2.0","prompt":"A red circle gently pulsing on a white background","num_frames":81,"frame_rate":24}'

   Verify the response includes a `video_id` and a `status` (e.g. `queued`).

6. Poll for the result (wait ~15s first), replacing the id:

     curl -s --location --request GET \
       'https://apihub.agnes-ai.com/agnesapi?video_id=YOUR_VIDEO_ID' \
       --header "Authorization: Bearer $AGNES_AI_API_KEY"

   Verify the task transitions through `queued`/`in_progress` and eventually
   `completed` with a `metadata.url`. A valid in-progress state also passes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: RUN THE BUNDLED QC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

7. Run the install QC script and confirm it exits 0:

     bash qc-agnes-video.sh

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: APPLY CORE FILE UPDATES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

8. Apply only the labeled sections in CORE_UPDATES.md to AGENTS.md, TOOLS.md, and
   MEMORY.md. Add a lean pointer to agnes-video-full.md — do NOT paste the full
   reference into core files. Touch NO other core files.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before telling the user setup is complete, verify ALL of these:

[ ] Skill folder present with all listed files
[ ] agnes-video-full.md read in full
[ ] AGNES_AI_API_KEY confirmed SET (value never printed)
[ ] (optional) self-test task created and polled to a valid state
[ ] qc-agnes-video.sh exited 0
[ ] CORE_UPDATES.md applied surgically (lean pointer only)

DO NOT tell the user setup is complete until the checklist is satisfied.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO ADD TO YOUR CORE FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

See CORE_UPDATES.md for the exact labeled text. Summary:

[ADD TO AGENTS.md]
## Agnes Video V2.0 — Text/Image/Keyframe Video
- Model: agnes-video-v2.0. ASYNC: POST /v1/videos to create, then poll
  GET /agnesapi?video_id=<id>. Auth: Bearer AGNES_AI_API_KEY (referenced, never printed).
- num_frames <= 441 and on the 8n+1 grid; trust returned size/seconds, not the request.
- Full reference: [MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

If any step here appears to require restarting the OpenClaw gateway, DO NOT run
it yourself. STOP, tell the user a restart is needed, instruct them to type
`/restart` in Telegram, and WAIT for confirmation. This skill does not require a
restart for normal use.
