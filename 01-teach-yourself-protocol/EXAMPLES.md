# Teach Yourself Protocol - Examples

## Example 1: Large API Reference (Layer 2 + Layer 1)

**User says:** "Here is the KIE.ai API reference. Learn this." (176K chars)

**Agent process:**
1. Announces TSP activation
2. Category: API reference. Priority: CRITICAL. Size: Very Large.
3. Searches core files and master folder - no existing KIE.ai knowledge found
4. Creates deep file: `[MASTER_FILES_FOLDER]/apis/kie-ai/kie-ai-api-reference.md` (full 176K, untruncated)
5. Writes 20-line summary in TOOLS.md: auth method, base URL, rate limit, pricing, model list, common pitfalls, file path, "when to go deeper" triggers
6. Writes memory entry in MEMORY.md: "KIE.ai API learned [date]. Full doc at [path]."
7. Confirms to user: what was stored, where, which files updated

**Does NOT:** Paste 176K into TOOLS.md. Create a duplicate folder. Skip announcement.

## Example 2: Short Preference (Layer 1 Only)

**User says:** "Never use em dashes in any output."

**Agent process:**
1. Announces TSP activation
2. Category: Preference/rule. Priority: CRITICAL. Size: Small (one rule).
3. Searches core files - no existing em dash rule found
4. No deep file needed (under 25 lines)
5. Adds rule directly to AGENTS.md, TOOLS.md, IDENTITY.md
6. Adds to MEMORY.md with date
7. Confirms

**Does NOT:** Create a deep file for one sentence. Skip searching for existing rules.

## Example 3: Multi-Part Knowledge Base (Layer 3 + Layer 2 + Layer 1)

**User shares:** 14 skill files from a GitHub repository

**Agent process:**
1. Announces TSP
2. Category: Skills/knowledge base. Priority: HIGH. Size: Massive (14 files, multiple topics).
3. Creates folder structure: `[MASTER_FILES_FOLDER]/superpowers/skills/` with 14 subfolders
4. Stores all files unabridged in their subfolders
5. Behavioral rules (Iron Laws) go directly in AGENTS.md (they ARE behavioral rules)
6. Tool trigger map goes in TOOLS.md
7. Install record goes in MEMORY.md
8. Confirms: 14 skills stored, 3 core files updated, full docs at [path]

## Example 4: Correcting Existing Knowledge (Update, Not Duplicate)

**User says:** "Use 'calendar' not 'calendar.readonly' for Google API scope."

**Agent process:**
1. Announces TSP
2. Category: Correction. Priority: CRITICAL. Size: Small.
3. Searches core files - finds old scope in TOOLS.md and MEMORY.md
4. UPDATES existing entries (does not create new ones)
5. Updates deep file if one exists with the old value
6. Confirms: "Updated Google API scope from calendar.readonly to calendar in TOOLS.md and MEMORY.md"

**Does NOT:** Create a second entry alongside the old one. Leave the old value in place.

## Example 5: Implicit Trigger (File Shared Without Instructions)

**User uploads a PDF and says:** "here you go"

**Agent process:**
1. Reads the file to understand what it is
2. Recognizes implicit TSP trigger
3. Confirms: "This looks like [description]. I am activating TSP to store this permanently. Let me know if this is just for this session."
4. If user confirms or says nothing, follows standard TSP process
5. If user says "just for now", skips TSP

**Key:** When trigger is implicit, confirm before executing.
