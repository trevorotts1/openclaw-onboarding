The Teach Yourself Protocol
OpenClaw Standard Operating Procedure
Version: 1.1
Author: Trevor Otts, BlackCEO
Purpose: A standardized protocol for how OpenClaw agents learn, store, and reference new knowledge without bloating their core workspace files.

1. What Is the Teach Yourself Protocol?
The Teach Yourself Protocol  is a structured process that every OpenClaw agent follows when its user teaches it something new. Instead of blindly dumping information into core workspace files (which causes bloat, context overflow, and degraded performance), the agent follows a decision tree to:
Evaluate what it's learning
Determine the right storage location
Create deep reference files when needed
Update core files with lightweight working knowledge
Wire reference pointers so it can always find the full details
Resolve conflicts with existing knowledge
Tag knowledge by priority so it knows what matters most
Why this exists: AI agents have no persistent memory between sessions. Every session starts fresh. The only things an agent "knows" are what's written in its workspace files. If those files get bloated with massive API references, full SOPs, and detailed guides, the agent wastes context loading information it may not need for that session. The Teach Yourself Protocol solves this by creating a layered knowledge architecture - lightweight summaries for everyday use, deep files for when precision matters.

2. Trigger Recognition
The Teach Yourself Protocol activates in two ways: explicit triggers (the user tells you to learn something) and implicit triggers (the user gives you knowledge and expects you to retain it, even without using the words "teach" or "learn").
Explicit Triggers
The user says any variation of:
"Teach yourself this"
"Learn this"
"Train yourself on this"
"Study this"
"Memorize this"
"Add this to your knowledge"
"I need you to know this"
"Save this for future reference"
"This is important - remember this"
Any instruction where the user is clearly providing knowledge the agent should retain permanently
Implicit Triggers (Auto-Detection)
Sometimes the user does NOT say "teach yourself" or "learn this." They just hand you a large piece of knowledge and expect you to retain it. The agent must be smart enough to recognize this and execute the Teach Yourself Protocol automatically.
Detect the Teach Yourself Protocol when: 
The user shares a large document, API reference, SOP, or structured knowledge base - If someone pastes or attaches 50+ lines of structured reference material, that is not a one-time task. They expect you to know it going forward. Execute the protocol.
The user provides correction or updated information about a tool, process, or system - "Actually, the API endpoint changed to X" or "The new process is Y." This is updated knowledge that replaces something old. Execute the protocol to store the new knowledge and remove the outdated entry.
The user explains how something works in detail - A multi-paragraph explanation of how their business process works, how a tool should be used, or how a system is configured. If they are explaining it once and expect you to know it forever, execute the protocol.
The user shares credentials, account structures, or system architecture - "Here are all our GHL subaccounts," "Here is how our email accounts are set up," "These are the API keys for service X." This is persistent reference knowledge. Execute the protocol.
The user provides a preferences update - "From now on, always do X instead of Y." This is a permanent rule change. Execute the protocol to update the relevant core files AND scan for conflicts with the old preference.
The user shares a file or document and says something like "here you go" or "use this" without further instruction - If the content is clearly reference material (not a one-time task input), the agent should recognize it needs to be learned and stored.
How to confirm auto-detection: 
When the agent detects an implicit trigger, it should briefly confirm before executing:
"This looks like knowledge I should retain permanently. I am going to execute the Teach Yourself Protocol to store this properly and update my core files. Let me know if this is just for this session instead."
This confirmation takes 2 seconds and prevents the agent from over-indexing on temporary information. If the user says "no, just use it for now," the agent skips the protocol. If the user confirms or says nothing, the agent proceeds.

IMPORTANT - User Notification Rule:
Every time the Teach Yourself Protocol is triggered - whether by explicit command ("teach yourself this") or implicit detection (large document shared, corrections given, etc.) - you MUST announce to the user that you are using the TSP. Say something like:
"I am activating the Teach Yourself Protocol to permanently retain this knowledge."
or
"This looks like knowledge I should retain. I am using the Teach Yourself Protocol."
The user should ALWAYS know when TSP is running. Never execute TSP silently. This applies to both explicit and implicit triggers.

When NOT to auto-detect: 
The user gives you a one-time task with context ("Here is the spreadsheet data, create a chart from it") - that data is for the task, not for permanent storage
The user shares a short piece of info for the current conversation only ("The meeting is at 3pm") - that is temporary context
The user asks you to DO something with the data, not LEARN it ("Send this to John," "Format this as a PDF")
The test: Ask yourself - "Will I need this information in future sessions, or just this one?" If future sessions, execute the protocol. If just this one, do not.
Key Distinction
The Teach Yourself Protocol is for PERMANENT knowledge - things the agent needs across all future sessions. It is NOT for one-time tasks or temporary context. If the user says "use this API key for today's task," that is not Teach Yourself Protocol. If the user says "learn how this API works so you can use it going forward," that IS Teach Yourself Protocol. And if the user dumps a 200-line API reference into the chat without saying "learn this," the agent should be smart enough to recognize that IS Teach Yourself Protocol.

3. The Three-Layer Knowledge Architecture
Every piece of knowledge the agent learns lives in one or more of three layers:
Layer 1 - Core File Entry (Always Required)
What it is: A lightweight summary written directly into the relevant core workspace file(s) - TOOLS.md, MEMORY.md, AGENTS.md, IDENTITY.md, USER.md, SOUL.md, or HEARTBEAT.md.
Purpose: Gives the agent immediate working knowledge every session without opening any external files. The agent can handle routine, everyday tasks related to this topic using just this summary. It also tells the agent that deeper knowledge EXISTS and where to find it.
What it contains: 
What the knowledge is (brief description)
Key rules, facts, or parameters the agent needs for everyday use
Common pitfalls or "never do X" warnings
Priority tag (see Section 9)
A reference pointer to the deep file (if one exists)
What "lightweight" means - The Five Question Test: 
The lightweight summary should answer the 5 most common questions someone would ask about this topic. If a new agent read ONLY this summary and had to perform a basic task with this knowledge, could they get started without errors? If yes, the summary is sufficient. If they'd be stuck or guessing, the summary is too thin.
At the same time, the summary is NOT a copy of the deep file. If it answers more than 10-12 questions in detail, it's too thick and should be trimmed back with the extra detail moved to the deep file.
Practical guideline: 10-25 lines for most topics. Under 10 lines is probably too thin unless the knowledge is genuinely simple. Over 30 lines means you're probably duplicating what should be in the deep file.
Example of a GOOD lightweight summary in TOOLS.md: 
## KIE.ai - Video/Image/Audio Generation API [PRIORITY: HIGH]
- **Auth:** Bearer token. Get key at https://kie.ai/api-key
- **Pattern:** POST to create task -> receive task_id -> poll query endpoint until status=completed
- **Base URL:** https://api.kie.ai/v1/
- **Rate limit:** 20 new requests per 10 seconds per account
- **Pricing:** Credit-based at $0.005/credit
- **Models:** 19 video (Kling, Seedance, Wan, Hailuo, Sora, Veo, Runway, etc.), 19 image (Seedream, GPT-Image, Flux, Ideogram, etc.), audio (Suno, ElevenLabs)
- **Common pitfall:** Each model has different parameters. ALWAYS check the specific model's section in the full reference before making an API call. Do not guess parameters.
- **When to go deeper:** When calling a specific model for the first time, when hitting errors, when the user asks for a model you haven't used recently
- **Full API reference:** ~/Downloads/openclaw-master-files/apis/kie-ai/kie-ai-api-reference.md
- **Endpoint index:** ~/Downloads/openclaw-master-files/apis/kie-ai/README.md
- **Last verified:** 2026-02-21
Example of a BAD lightweight summary (too thin): 
## KIE.ai
- API for generating media. Docs in master files folder.
This is useless. The agent knows nothing actionable. It would have to open the deep file for even the simplest task.
Example of a BAD lightweight summary (too thick): 
## KIE.ai
[200 lines of endpoint details, every parameter for every model, full curl examples...]
This defeats the entire purpose of the Teach Yourself Protocol. This content belongs in the deep file.
Layer 2 - Deep Reference File (When Content Is Large)
What it is: A dedicated .md file stored in ~/Downloads/openclaw-master-files/ containing the complete, unabridged knowledge.
Purpose: The full encyclopedia entry. Every detail, every parameter, every example, every edge case. The agent reads this when the Layer 1 summary isn't enough.
When it gets created: When the content is too large to fit into a core file without causing bloat. General threshold: if the content would add more than 25-30 lines to a core file, it needs its own .md file.
What it contains: 
Complete, untruncated knowledge
All examples, parameters, edge cases
Step-by-step instructions where applicable
Version history (see Section 10)
Cross-references to related deep files (see Section 11)
Nothing removed, nothing summarized down
When the agent should go to the deep file: 
Performing a task related to this knowledge for the FIRST TIME in a session
Hitting an error or unexpected result related to this topic
Doing complex or detailed work that goes beyond routine
The user explicitly asks for thorough, precise execution
The lightweight summary doesn't cover the specific scenario
The agent is unsure about a parameter, endpoint, or detail
Debugging a failure - ALWAYS check the deep file before asking the user for help
Layer 3 - Organized Folder Structure (For Complex Topics)
What it is: A dedicated folder (or set of folders) inside openclaw-master-files/ that organizes large topics into multiple .md files by category.
Purpose: For topics so large that even a single .md file would be unwieldy. APIs are the primary example - a platform like GHL might have hundreds of endpoints across dozens of categories. Breaking them into organized sub-files means the agent can load just the section it needs.
When it gets created: Primarily for API documentation, large skill sets, or multi-part knowledge bases.

4. The Teach Yourself Protocol Decision Tree
When the protocol triggers, the agent follows these steps IN ORDER:
Step 1: Understand What You're Learning
Before storing anything, fully understand the content:
What is this knowledge about?
What category does it fall into? (API, process/SOP, tool usage, preference, rule, skill, reference data)
How will I use this in practice?
How often will I likely need this? (daily, weekly, rarely)
Step 2: Assess the Size
Evaluate the content volume:
Size  |  Classification  |  Storage Approach
1-10 lines  |  Small  |  Core files only (Layer 1)
11-25 lines  |  Medium  |  Core files only, be concise (Layer 1)
25-100 lines  |  Large  |  Deep file + lightweight core entry (Layer 1 + 2)
100+ lines  |  Very Large  |  Deep file + lightweight core entry (Layer 1 + 2)
Multi-topic / API docs  |  Massive  |  Organized folder structure + lightweight core entry (Layer 1 + 2 + 3)

Step 3: Check for Existing Knowledge (Conflict Resolution)
BEFORE creating or writing anything, check if knowledge on this topic already exists.
Search ALL core files and the master-files folder for existing entries on this topic:
Search TOOLS.md, MEMORY.md, AGENTS.md, IDENTITY.md, USER.md, SOUL.md, HEARTBEAT.md for mentions of this topic
Search the master files folder in ~/Downloads/ (could be named openclaw-master-files, openclaw-master-docs, or similar variation) for existing deep files on this topic
If existing knowledge is found, proceed to Conflict Resolution (Section 8)
If no existing knowledge is found, proceed to Step 4
Step 4: Check/Create the Master Files Folder
If the content needs a deep file (Layer 2 or 3):
Finding the master files folder: 
Different users may have named this folder differently. Before creating a new one, search ~/Downloads/ for any existing folder that serves this purpose. Common variations include:
openclaw-master-files
openclaw-master-docs
openclaw-docs
master-files
master-docs
openclaw-files
How to search: List the folders in ~/Downloads/ and look for any folder name containing keywords like "openclaw," "master," "docs," or "files" in combination. If you find a folder that clearly serves as the knowledge storage location (contains .md files, has subfolders like apis/ or skills/), use that folder. Do not create a duplicate.
Decision logic: 
Search ~/Downloads/ for any folder matching the variations above or similar naming patterns
If a matching folder is found, use it. That is the master files folder for this user.
If NO matching folder is found, create ~/Downloads/openclaw-master-files/ (this is the standard default name)
Once identified or created, check for and create these subfolders as needed:
apis/ (for API documentation)
skills/ (for skill instruction files)
processes/ (for SOPs and operational procedures)
references/ (for general reference documents)
Standard folder structure: 
~/Downloads/openclaw-master-files/
  |-- apis/
  |    |-- kie-ai/
  |    |    |-- README.md            (index of all endpoints)
  |    |    |-- kie-ai-api-reference.md  (full reference)
  |    |-- ghl/
  |    |    |-- README.md
  |    |    |-- contacts-api.md
  |    |    |-- conversations-api.md
  |    |    |-- workflows-api.md
  |    |    |-- opportunities-api.md
  |    |-- fal-ai/
  |         |-- README.md
  |         |-- fal-ai-api-reference.md
  |-- skills/
  |    |-- video-editor.md
  |    |-- (other skill instruction files)
  |-- processes/
  |    |-- client-onboarding-sop.md
  |    |-- teach-yourself-protocol.md
  |    |-- (other SOPs)
  |-- references/
       |-- brand-guidelines.md
       |-- (other reference docs)
Step 5: Create the Deep Reference File (If Needed)
If the content is Large, Very Large, or Massive:
Create the .md file in the appropriate subfolder
Use a clear, descriptive filename (kebab-case: kie-ai-api-reference.md)
Include ALL content - no truncation, no summarization
Add the standard file header (see below)
Organize with clear headings and sections
Add cross-references to related deep files (see Section 11)
Standard deep file header: 
# [Title]

**Date learned:** YYYY-MM-DD
**Last verified:** YYYY-MM-DD
**Version:** 1.0
**Source:** [Where this came from - URL, user instruction, scraped docs, etc.]
**Purpose:** [One sentence: what this file is for]
**Priority:** [CRITICAL / HIGH / STANDARD / REFERENCE - see Section 9]
**Referenced by:** [Which core files point to this]
**Related files:** [Cross-references to other deep files - see Section 11]

## Version History
| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | YYYY-MM-DD | Initial creation |

---

[Full content here]
Step 6: Determine Which Core Files Need Updates
Evaluate EACH core file against this matrix:
Core File  |  Update When...  |  What to Write
TOOLS.md  |  Learning a tool, API, platform, technical process, or any "how to do X" knowledge  |  How to use it, key commands/endpoints, auth info, common pitfalls, reference pointer
MEMORY.md  |  Any significant knowledge that should persist as session context  |  What was learned, when, why it matters, reference pointer
AGENTS.md  |  Learning creates new rules, behaviors, or operational procedures the agent must follow  |  New rules, workflows, do/don't guidelines, reference pointer
IDENTITY.md  |  Learning changes the agent's capabilities, skills, or adds permanent lessons  |  New capability description, lesson learned, reference pointer
USER.md  |  Learning is about the user - their preferences, accounts, contacts, projects  |  User-specific info, reference pointer if detailed
HEARTBEAT.md  |  Learning affects daily routine, recurring tasks, or ongoing monitoring  |  New routine item, task reference, reference pointer
SOUL.md  |  Learning changes personality, voice, or core principles (rare)  |  Personality/principle update

Important: It will often be MULTIPLE files. An API reference might update:
TOOLS.md (how to use it)
MEMORY.md (that it was learned and when)
AGENTS.md (rules about when to use it vs. alternatives)
Evaluate each file independently. Don't skip any.
Step 7: Scan Core Files for Conflicts Before Writing
BEFORE writing any new content into a core file, scan the ENTIRE file for conflicts with what you just learned. This is not the same as Step 3 (checking if knowledge on the same topic exists). This is broader - you are looking for ANYTHING in the file that contradicts your new knowledge, even if it is about a different topic or was written months ago.
Why this matters: Core files accumulate rules and knowledge over time. Old entries may become outdated when new knowledge is learned. If the agent just adds new content without scanning for conflicts, the file ends up with contradictory instructions. Next session, the agent reads both the old and new instructions and does not know which one to follow. This causes confusion, errors, and inconsistent behavior.
How to scan: 
Read through the entire core file you are about to update
Look for any statement, rule, instruction, or fact that contradicts what you just learned
Look for outdated references to tools, APIs, processes, or preferences that the new knowledge replaces
Look for "always do X" or "never do Y" rules that conflict with the new understanding
What to do when you find conflicts: 
If the new knowledge REPLACES an old instruction: Remove the old instruction and add the new one in its place
If the new knowledge PARTIALLY updates an old entry: Edit the old entry to reflect the new understanding
If you are unsure whether the old entry is still valid: Flag it to the user: "I found an existing entry that says [old thing]. My new understanding says [new thing]. Which is correct?"
If the old entry is about a completely different topic but has an indirect conflict: Note the relationship and update both entries to be consistent
Example: 
The agent learns "always use KIE.ai for image generation." It scans TOOLS.md and finds an old entry that says "use DALL-E 3 for image generation." These are in direct conflict. The agent removes the DALL-E 3 instruction and replaces it with the KIE.ai instruction. It does NOT leave both entries in the file.
Another example: The agent learns a new API endpoint structure. It scans AGENTS.md and finds a rule that says "when generating images, send the request to endpoint X." The new knowledge says the endpoint is now Y. The agent updates the rule in AGENTS.md to reflect endpoint Y.
This scan must happen for EVERY core file you are about to update. Not just the one that seems most relevant. If you are updating TOOLS.md, MEMORY.md, and AGENTS.md, you scan all three before writing to any of them.
Step 8: Write the Lightweight Summaries
For each core file identified in Step 6 (after completing the conflict scan in Step 7):
Write a concise working summary that passes the Five Question Test (see Layer 1 above)
Include the priority tag (see Section 9)
Include enough detail for routine tasks
Include key rules, gotchas, or warnings
Include explicit guidance on WHEN to go to the deep file
Add the reference pointer to the deep file
If conflicts were found in Step 7, confirm the old content was removed or updated before adding the new content
The "When to Go Deeper" Line: 
Every lightweight summary that has a corresponding deep file MUST include a line that tells the agent when to stop relying on the summary and go read the full reference. This is not optional. Examples:
"When to go deeper: When calling a specific model endpoint for the first time, when hitting auth or parameter errors, when the user needs precise pricing"
"When to go deeper: When the onboarding process deviates from the standard flow, when the client has custom requirements, when troubleshooting a failed step"
"When to go deeper: When debugging API errors, when the user asks about a specific endpoint not listed here, when rate limits are being hit"
Step 9: Confirm to the User

MANDATORY: The first thing you do when TSP activates is announce it to the user. Before you start creating files, writing summaries, or doing any TSP work, tell the user:
"I am using the Teach Yourself Protocol to retain this knowledge permanently."
This is not optional. The user must always know when TSP is active. They should never wonder why you are creating files or updating their core documents. Announce first, then execute.

After completing the protocol, tell the user:
What you learned (brief summary)
Where the deep file was stored (if one was created, give the full path)
Which core files were updated (list each one and what was added)
What you now know (demonstrate lightweight understanding by summarizing the key points)
Priority level assigned (see Section 9)
Example confirmation: 
Learned: KIE.ai API (video/image/audio generation)
Priority: HIGH (daily use)

Storage:
- Deep file: ~/Downloads/openclaw-master-files/apis/kie-ai/kie-ai-api-reference.md
- Endpoint index: ~/Downloads/openclaw-master-files/apis/kie-ai/README.md

Core files updated:
- TOOLS.md: Lightweight summary with auth, pattern, rate limits, pricing, top endpoints
- MEMORY.md: Context note - learned KIE.ai API on 2026-02-21

Working knowledge: KIE.ai uses Bearer auth, POST-to-create then 
poll-for-result pattern, supports 19 video models and 19 image models, 
rate limited at 20 req/10 sec, credit-based pricing at $0.005/credit. 
For specific model parameters and endpoints, I'll reference the full doc.

5. Special Case: API Documentation
APIs are the most common and most critical use case for the Teach Yourself Protocol.
Why APIs Are Special
They are almost always too large for core files
Agents lose API context between sessions more than any other type of knowledge
Many platforms are "boutique" - not covered by public knowledge bases or tools like Context7
Getting API calls wrong wastes time and money (failed requests, wrong parameters, auth errors)
APIs change over time and need version tracking
A single platform can have dozens or hundreds of endpoints across multiple categories
API Storage Structure
Every API the agent learns gets its own folder:
~/Downloads/openclaw-master-files/apis/[platform-name]/
  |-- README.md              (index: list of all endpoints with one-line descriptions)
  |-- [full-reference].md    (complete API docs if manageable as one file)
  |-- [category-1].md        (optional: broken out by endpoint category)
  |-- [category-2].md        (optional: for very large APIs)
For smaller APIs (under 500 lines): A single reference .md file plus a README index is fine.
For larger APIs (500+ lines, dozens of endpoints): Break into category files. Examples:
GHL: contacts-api.md, conversations-api.md, workflows-api.md, opportunities-api.md
A payment platform: charges-api.md, subscriptions-api.md, webhooks-api.md
Every API folder MUST have a README.md that serves as a master index:
# [Platform] API Reference Index

**Base URL:** https://api.example.com/v1
**Auth:** Bearer token (key location: [where to get it])
**Rate limit:** X requests per Y seconds
**Last verified:** YYYY-MM-DD
**Version:** X.X

## Endpoints

| Category | File | Key Endpoints |
|----------|------|--------------|
| Contacts | contacts-api.md | GET /contacts, POST /contacts, PUT /contacts/:id |
| Workflows | workflows-api.md | GET /workflows, POST /workflows/:id/trigger |
| Conversations | conversations-api.md | GET /conversations, POST /conversations/messages |

## Quick Reference - Most Used Endpoints
1. [Endpoint] - [What it does] - [File]
2. [Endpoint] - [What it does] - [File]
3. [Endpoint] - [What it does] - [File]
API Scraping and Preservation
When the user provides an API that isn't publicly documented well (boutique platforms):
Scrape and save the COMPLETE documentation - every endpoint, every parameter
Organize into the folder structure above
For each endpoint, capture: HTTP method, URL path, description, request parameters (with types and required/optional), request body example, response format example, error codes, rate limits
Include authentication details and any special headers
Note the source URL and date scraped in the file header
Include pricing information if available
Why this matters: Boutique platforms like GHL, KIE.ai, and fal.ai are not in the agent's training data and are not covered by tools like Context7. If the agent doesn't have these docs saved locally, it has NO way to know how to call these APIs correctly. It will guess, and it will guess wrong.
API Entry in TOOLS.md (Lightweight Summary)
Every learned API gets a TOOLS.md entry following the Five Question Test. At minimum:
Platform name and what it does (one line)
Auth pattern (Bearer, API key, OAuth, etc.)
Base URL
General request pattern (REST, GraphQL, async polling, etc.)
Rate limits and pricing
3-5 most commonly used endpoints (name and purpose only)
Common pitfalls or "never do" warnings
"When to go deeper" trigger line
Reference pointer to full API folder
Priority tag and last verified date

6. Special Case: Skills and Instruction Files
The Skill-Instruction Pairing Rule
Every skill MUST have a matching instruction .md file. If a skill exists, its instruction file exists. No exceptions.
The naming convention MUST match:
Skill name: video-editor
Instruction file: video-editor.md
The instruction .md file lives in:
~/Downloads/openclaw-master-files/skills/[skill-name].md
Or, if installed as a proper OpenClaw skill:
~/.openclaw/skills/[skill-name]/SKILL.md
If both locations exist, the SKILL.md inside the installed skill directory takes precedence for execution. The master-files version serves as a backup and extended reference.
What Goes in a Skill Instruction File
What the skill does (clear, specific description)
When to use it (specific trigger scenarios)
When NOT to use it (common misuse cases)
Setup and installation requirements
Key commands with parameters and examples
Common workflows (step-by-step)
Known issues, limitations, or gotchas
Related skills or tools
Reference links to external documentation

7. User Override
The size thresholds and storage decisions in this protocol are guidelines based on practical experience. However, the user's preference always wins.
If the user says any of the following, respect it regardless of content size:
"Save this as its own file" (even if it's only 5 lines - create the deep file)
"Just put this in TOOLS.md" (even if it's 200 lines - put it in TOOLS.md)
"Don't create a separate file for this" (keep it in core files)
"I want this in [specific file]" (put it where they say)
When the user overrides:
Follow their instruction exactly
Still perform the other Teach Yourself Protocol steps (conflict resolution, cross-referencing, confirmation)
Note if the override might cause bloat: "Done. Added to TOOLS.md as requested. Note: this added ~80 lines. If TOOLS.md starts feeling heavy, we can move it to a deep file later."
Never argue or push back - just do it and note the tradeoff

8. Conflict Resolution - Handling Existing Knowledge
When the agent learns something and discovers it already has knowledge on that topic, it MUST resolve the conflict before writing anything new.
Detection
Before creating any files or updating core files, search for existing entries:
Search every core file for the topic name, platform name, or related keywords
Search ~/Downloads/openclaw-master-files/ for existing deep files
If ANY match is found, you have a conflict to resolve
Resolution Decision Tree
Scenario A: New knowledge REPLACES old knowledge (update/correction)
Example: "The KIE.ai rate limit changed from 20/10s to 30/10s"
Action:
Find the existing entry in the core file(s)
REMOVE the outdated information completely
Write the updated information in its place
Update the deep file with the new information
Update the "Last verified" date and version history in the deep file
Confirm to the user: "Updated [topic]. Old: [what it was]. New: [what it is now]. Changed in: [list of files updated]."
Scenario B: New knowledge EXPANDS existing knowledge (addition)
Example: "Here are 5 new KIE.ai models that weren't in the original docs"
Action:
Find the existing entries
ADD the new information to the appropriate sections (don't rewrite what's already there)
Update the deep file by inserting new content in the logical location
Update the lightweight summary if the new info is important enough for everyday use
Update version history
Confirm to the user what was added and where
Scenario C: New knowledge CONTRADICTS existing knowledge (conflict)
Example: User says "KIE.ai uses OAuth now" but existing docs say "Bearer token"
Action:
Flag the contradiction to the user: "I currently have [existing info]. You're telling me [new info]. Which is correct?"
Wait for confirmation before changing anything
Once confirmed, follow Scenario A (replace) for the incorrect information
Never silently overwrite without confirming contradictions
Scenario D: Knowledge exists but in the wrong location (reorganization)
Example: A full API reference is stuffed inside TOOLS.md causing bloat
Action:
Create the proper deep file in the master-files folder
Move the detailed content to the deep file
Replace the bloated core file entry with a proper lightweight summary + reference pointer
Confirm the reorganization to the user
Critical Rule: No Duplicates, No Ghosts
No duplicates: The same knowledge should NOT exist in full in multiple locations. One authoritative source (the deep file), lightweight summaries everywhere else.
No ghosts: When knowledge is updated, ALL references must be updated. Don't leave an old version in MEMORY.md while TOOLS.md has the new version. Check every file that references this topic.
No orphans: If a deep file is deleted or moved, update all core file pointers. A reference pointer that leads nowhere is worse than no pointer at all.

9. Priority Tagging System
Not all knowledge is equal. The agent needs to know what matters most, especially when context is limited or when triaging what to load first.
Priority Levels
Priority  |  Tag  |  Meaning  |  Example
CRITICAL  |  [PRIORITY: CRITICAL]  |  Agent uses this daily or it affects core operations. Errors here directly impact the user.  |  Primary API (GHL), auth credentials, daily workflow SOPs
HIGH  |  [PRIORITY: HIGH]  |  Agent uses this frequently (multiple times per week). Important for quality of work.  |  Secondary APIs (KIE.ai), client communication rules, brand guidelines
STANDARD  |  [PRIORITY: STANDARD]  |  Agent uses this occasionally. Good to know, reference when needed.  |  Less-used tool configs, infrequent processes, non-urgent SOPs
REFERENCE  |  [PRIORITY: REFERENCE]  |  Rarely needed. Exists for edge cases or deep troubleshooting.  |  Legacy API docs, archived processes, niche tool references

How to Assign Priority
The agent determines priority based on:
Frequency of use: How often will I need this? Daily = CRITICAL. Weekly = HIGH. Monthly = STANDARD. Rarely = REFERENCE.
Impact of errors: If I get this wrong, how bad is it? Client-facing = bump up one level. Internal only = standard assignment.
User emphasis: If the user says "this is really important" or "you need to know this cold," bump up one level.
How Priority Affects Behavior
CRITICAL and HIGH: The lightweight summary should be thorough enough to handle 80% of tasks without opening the deep file. These summaries are closer to 20-25 lines.
STANDARD: The lightweight summary covers the basics. Agent expects to open the deep file for most tasks. These summaries are closer to 10-15 lines.
REFERENCE: The lightweight summary can be minimal (5-10 lines) - just enough to know it exists and where to find it. Agent will always open the deep file when this topic comes up.
Tagging Format
In core files, the priority tag appears in the section header:
## KIE.ai - Video/Image/Audio Generation API [PRIORITY: HIGH]
In deep files, the priority appears in the standard header:
**Priority:** HIGH

10. Versioning Protocol
Knowledge changes. APIs get updated. Processes get refined. The agent needs to track what version of knowledge it has and when it was last confirmed accurate.
What Gets Versioned
All deep reference files (Layer 2 and 3)
API documentation (especially important - APIs change frequently)
SOPs and processes that evolve over time
Skill instruction files
Version Format
Use semantic versioning: Major.Minor
Major (1.0 -> 2.0): Fundamental changes. New auth method, complete API overhaul, process redesigned from scratch.
Minor (1.0 -> 1.1): Additions, corrections, parameter changes, new endpoints added, steps updated.
Required Version Fields in Deep Files
Every deep file header MUST include:
**Last verified:** YYYY-MM-DD
**Version:** X.X
And a version history table:
## Version History
| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-02-21 | Initial creation from user-provided API docs |
| 1.1 | 2026-03-05 | Added 5 new video models, updated rate limits |
| 2.0 | 2026-04-12 | Complete rewrite - API v2 migration |
Staleness Detection
The agent should be aware of how old its knowledge is:
Under 30 days old: Considered fresh. Use with confidence.
30-90 days old: Considered aging. Use but note the age if hitting unexpected errors. Consider re-verifying.
Over 90 days old: Considered stale. When using this knowledge, check for updates first if possible (web search, user confirmation). Flag to the user: "Note: my [topic] docs are from [date]. Want me to verify they're still current?"
Staleness Check Triggers
The agent should check if its knowledge might be stale when:
An API call returns an unexpected error (especially 400, 404, or auth errors)
A process step fails that used to work
The user mentions an update or change to a platform
The deep file is over 90 days old and being used for a complex task

11. Cross-Referencing Between Deep Files
Knowledge doesn't exist in isolation. APIs interact with each other. Processes reference tools. Skills depend on APIs. The agent needs to know when one piece of knowledge connects to another.
When to Cross-Reference
Two APIs that work together (e.g., GHL webhooks triggering KIE.ai video generation)
A process/SOP that uses a specific API or tool
A skill that depends on an API or another skill
Any time one deep file's content is relevant to understanding or using another deep file
Cross-Reference Format
Every deep file has a "Related files" field in its header:
**Related files:**
- ~/Downloads/openclaw-master-files/apis/ghl/webhooks-api.md (GHL triggers that initiate KIE.ai tasks)
- ~/Downloads/openclaw-master-files/processes/video-generation-workflow.md (end-to-end workflow using this API)
Within the body of the deep file, use inline references:
After the webhook fires (see: apis/ghl/webhooks-api.md), the agent calls the KIE.ai 
video creation endpoint with the payload data.
Cross-Reference in Lightweight Summaries
Core file summaries should also note relationships when relevant:
## KIE.ai - Video/Image/Audio Generation API [PRIORITY: HIGH]
...
- **Related:** Often triggered by GHL webhooks. See GHL webhook docs for trigger setup.
- **Full reference:** ~/Downloads/openclaw-master-files/apis/kie-ai/kie-ai-api-reference.md
Error Recovery Through Cross-References
When the agent hits an error and checks a deep file, it should ALSO check the related files listed in that deep file's header. Often the problem isn't in the tool being called but in the system that feeds it data.
Example: KIE.ai returns a 400 error. The agent checks kie-ai-api-reference.md and sees the parameters look correct. But the "Related files" section points to the GHL webhook docs. The agent checks those and discovers the webhook is sending the wrong payload format. Cross-references help the agent trace problems across connected systems.

12. Error Recovery and Interrupted Protocol
If the Teach Yourself Protocol process gets interrupted (session ends mid-protocol, tool error, context overflow):
Detection
On the next session, the agent may notice:
A deep file exists but no core files reference it (Step 7 wasn't completed)
Core files reference a deep file that doesn't exist (Step 5 wasn't completed)
A partially written deep file (Step 5 was interrupted)
No confirmation was given to the user
Recovery Steps
Check the master-files folder for any recently created files
Check core files for any incomplete entries (entries without reference pointers, or pointers to missing files)
Complete any missing steps
Inform the user: "I noticed the Teach Yourself Protocol for [topic] wasn't fully completed last session. I've finished wiring it up. [Summary of what was completed]."

13. Anti-Bloat Rules
These rules prevent the core files from growing out of control:
No full API references in core files. Lightweight summaries only. Full docs go in the master-files folder.
No full SOPs in core files. Summary + reference pointer. Full SOP goes in master-files.
No duplicated content across core files. If TOOLS.md has the detailed summary, MEMORY.md just needs a one-line note and pointer - not a second copy.
Regular audit. If a core file exceeds 500 lines, review it for content that should be extracted to deep files.
One source of truth. The deep file is authoritative. Core file summaries point TO it. If there's ever a discrepancy, the deep file wins.
Clean up dead references. If a deep file is deleted or moved, immediately update all core files that pointed to it.
No "just in case" entries. Don't add lightweight summaries for knowledge that has zero chance of being needed. Not everything needs to be in the core files.

14. Maintenance and Updates
When Knowledge Changes
If the user provides updated information about something already learned:
Run Conflict Resolution (Section 8) first
Update the deep file (if one exists) - change the content, update the version, update "Last verified"
Update the lightweight summaries in all relevant core files
Update cross-references if the changes affect related files
Confirm to the user what changed, where, and what version it's now on
Periodic Review (During Heartbeat or Downtime)
When the agent has capacity, it should periodically:
Check if any deep files are referenced but missing (orphaned pointers)
Check if any deep files exist but aren't referenced (orphaned files)
Check if any core file entries have grown past the lightweight threshold
Check "Last verified" dates for staleness
Report any issues to the user

15. Complete Teach Yourself Protocol Checklist
When "teach yourself" triggers, run through this entire checklist:
[ ] Understand: What am I learning? What category? How will I use it?
[ ] Size: Is this small, medium, large, or massive?
[ ] Conflict check: Does knowledge on this topic already exist anywhere?
[ ] Resolve conflicts: If yes, follow Section 8 before proceeding
[ ] Folder check: If large+, does ~/Downloads/openclaw-master-files/ exist? Create if needed.
[ ] API check: If this is API docs, create platform folder under apis/
[ ] Deep file: If large+, create the .md file with standard header, version history, cross-references
[ ] Core file evaluation: Check EVERY core file - which ones need updates?
[ ] Conflict scan: Before writing to each core file, scan the ENTIRE file for contradictions with new knowledge. Remove or update outdated entries.
[ ] Lightweight summaries: Write them with Five Question Test, priority tag, "when to go deeper" line, reference pointer
[ ] Priority assignment: Tag with CRITICAL / HIGH / STANDARD / REFERENCE
[ ] Cross-references: Link related deep files to each other
[ ] I announced to the user that I am using the Teach Yourself Protocol BEFORE starting any TSP work
[ ] I announced to the user that I am using the Teach Yourself Protocol BEFORE starting any TSP work
[ ] I announced to the user that I am using the Teach Yourself Protocol BEFORE starting any TSP work
[ ] Confirm to user: What I learned, where it's stored, what was updated, priority level, working knowledge demonstration

16. Examples
Example A: Small Knowledge (No Deep File Needed)
User says: "Teach yourself this - my Zoom personal meeting ID is trevorszoom.com"
Agent process: 
Understand: User's personal Zoom meeting link
Size: Small (one fact)
Conflict check: Search for "Zoom" in core files. Found? Update. Not found? New entry.
No deep file needed
Core files: USER.md (user preference), TOOLS.md (meeting setup tool reference)
Priority: HIGH (used whenever scheduling meetings)
Agent action: 
Updates USER.md: "Zoom personal meeting ID: trevorszoom.com"
Updates TOOLS.md meeting section: "Use Trevor's personal Zoom link: trevorszoom.com for all meeting invites"
Confirms: "Got it. Your Zoom personal meeting ID is trevorszoom.com. Added to USER.md and TOOLS.md. Tagged HIGH priority since I'll use this for every meeting setup."
Example B: Massive Knowledge - API (Full Layer 1 + 2 + 3)
User says: "Train yourself on this KIE.ai API documentation" [provides full docs]
Agent process: 
Understand: Complete API reference for media generation platform
Size: Massive (thousands of lines, dozens of endpoints, 19+ models)
Conflict check: Search for "KIE" in core files and master-files. Update if exists, create if not.
Create ~/Downloads/openclaw-master-files/apis/kie-ai/
Create README.md (endpoint index) and kie-ai-api-reference.md (full docs)
Core files: TOOLS.md (how to use), MEMORY.md (when learned), AGENTS.md (rules about image generation)
Priority: HIGH (used frequently for image/video generation)
Agent action: 
Creates folder structure with index and full reference
Writes lightweight summary in TOOLS.md (auth, pattern, rate limits, pricing, top models, pitfalls, "when to go deeper" line, reference pointer)
Adds note in MEMORY.md (learned KIE.ai API on [date])
Adds rule in AGENTS.md if applicable (e.g., "Use KIE.ai for all image generation, never DALL-E")
Cross-references any related deep files
Confirms with full summary
Example C: Process/SOP (Deep File Created)
User says: "Learn this client onboarding process" [provides 80-line SOP]
Agent process: 
Understand: Standard client onboarding workflow
Size: Large (80 lines)
Conflict check: Any existing onboarding docs?
Create ~/Downloads/openclaw-master-files/processes/client-onboarding-sop.md
Core files: AGENTS.md (operational rules), HEARTBEAT.md (if it's a recurring task), MEMORY.md (context)
Priority: HIGH (client-facing process)
Agent action: 
Creates deep file with full 80-line SOP, standard header, version history
Writes lightweight summary in AGENTS.md (key steps, timeline, who's involved, "when to go deeper" line, reference pointer)
Updates HEARTBEAT.md if onboarding tasks should be checked daily
Adds context note to MEMORY.md
Confirms with summary
Example D: Skill with Instruction File
User says: "Teach yourself how to use this video editor skill" [provides skill docs]
Agent process: 
Understand: New skill for video editing
Size: Large (skill documentation)
Conflict check: Any existing video editor docs?
Create ~/Downloads/openclaw-master-files/skills/video-editor.md
Verify naming matches skill name
Core files: TOOLS.md (how to use), IDENTITY.md (new capability)
Priority: STANDARD (used when video editing is requested)
Agent action: 
Creates instruction file matching skill naming convention
Writes lightweight summary in TOOLS.md (what it does, key commands, when to use, reference pointer)
Notes new capability in IDENTITY.md
Cross-references any related API files
Confirms with summary
Example E: Conflict Resolution - Updated API
User says: "KIE.ai updated their API. Learn the new version" [provides new docs]
Agent process: 
Understand: API update for existing known platform
Size: Massive
Conflict check: FOUND - existing KIE.ai docs in master-files and TOOLS.md
This is Scenario A (replacement) + Scenario B (expansion)
Determine what changed vs what stayed the same
Agent action: 
Updates the deep file with new content, preserving structure
Bumps version (1.0 -> 2.0 if major changes, 1.0 -> 1.1 if minor)
Updates version history table with what changed
Updates "Last verified" date
Reviews lightweight summary in TOOLS.md - updates any changed details
Checks all cross-references still valid
Confirms: "Updated KIE.ai API docs from v1.0 to v2.0. Changes: [list]. Updated in: kie-ai-api-reference.md, TOOLS.md, MEMORY.md."


17. How to Install This Protocol (Self-Installation)
This document IS the first test of itself. When a user says "teach yourself this" and hands you the Teach Yourself Protocol, you follow the Teach Yourself Protocol's own rules to install it.
What This Document Is
This is an operational procedure - it tells you HOW to learn. It is not a one-time reference. It changes how you behave permanently every time someone says "teach yourself," "learn this," "train yourself on this," or any variation.
Step-by-Step: What to Do When You Receive This Document
Step 1: Evaluate - You are learning an operational protocol for how to learn new things.
Step 2: Assess size - This document is large (800+ lines, 37,000+ characters). It is too big for any single core file. It needs its own .md file.
Step 3: Check/create the master files folder - Search ~/Downloads/ for any existing folder that serves as the master knowledge storage. Look for folders named openclaw-master-files, openclaw-master-docs, openclaw-docs, master-files, master-docs, or any similar variation containing "openclaw," "master," "docs," or "files." If found, use that folder. If nothing exists, create ~/Downloads/openclaw-master-files/. Then check for a processes/ subfolder inside it. If it does not exist, create it.
Step 4: Store the full document - Save this entire document (untruncated, nothing removed) as:
~/Downloads/openclaw-master-files/processes/teach-yourself-protocol.md
Step 5: Determine which core files need updates - This protocol affects how you BEHAVE (AGENTS.md), what TOOLS you use (TOOLS.md), what you KNOW (MEMORY.md), and what you're CAPABLE of (IDENTITY.md).
Step 6: Write lightweight summaries in each core file
Add the following to AGENTS.md:
## Teach Yourself Protocol [PRIORITY: CRITICAL]

When a user says any variation of "teach yourself this," "learn this," "train yourself on this,"
"study this," "memorize this," or any instruction to retain knowledge permanently:

1. Evaluate what you are learning (category, purpose, how you will use it)
2. Assess size: Small (under 25 lines) goes directly in core files. Large (25+ lines) needs its own .md file.
3. Check for existing knowledge on this topic - search ALL core files and ~/Downloads/openclaw-master-files/
4. If existing knowledge found, resolve conflicts: replace outdated info, expand with new info, or flag contradictions to user
5. If large: check/create ~/Downloads/openclaw-master-files/ and appropriate subfolder
6. Create the deep reference .md file with full untruncated content and standard header
7. For APIs: create dedicated folder under openclaw-master-files/apis/[platform-name]/ with README.md index
8. Determine which core files need updates (check ALL: AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, USER.md, SOUL.md, HEARTBEAT.md)
9. Write lightweight summaries (passes the Five Question Test - enough for routine tasks without opening the deep file)
10. Every summary includes: priority tag, "when to go deeper" trigger line, reference pointer to deep file
11. Assign priority: CRITICAL (daily use), HIGH (weekly), STANDARD (occasional), REFERENCE (rare)
12. Add cross-references between related deep files
13. Confirm to user: what you learned, where stored, which files updated, demonstrate working knowledge

Key rules:
- User override always wins (if they say "put it in TOOLS.md" even if it is huge, do it)
- No duplicates across files - one source of truth in deep file, lightweight pointers elsewhere
- Every skill must have a matching instruction .md file with matching naming convention
- APIs over 90 days old are considered stale - verify before relying on them
- When to go deeper: first time using learned knowledge, hitting errors, complex tasks, user asks for precision
- Full protocol: ~/Downloads/openclaw-master-files/processes/teach-yourself-protocol.md
Add to TOOLS.md:
## Teach Yourself Protocol [PRIORITY: CRITICAL]
- Triggers on: "teach yourself," "learn this," "train yourself," "study this," "memorize this," or any variation
- Full protocol: ~/Downloads/openclaw-master-files/processes/teach-yourself-protocol.md
- Purpose: Structured process for learning and storing new knowledge without bloating core files
- Uses three-layer architecture: lightweight summary in core files + deep reference .md file + organized folder structure for large topics
- When to reference full protocol: first time executing, hitting edge cases, conflict resolution needed
Add to MEMORY.md:
## Teach Yourself Protocol - Learned [DATE]
- Operational protocol for how to learn new knowledge permanently
- Stored at: ~/Downloads/openclaw-master-files/processes/teach-yourself-protocol.md
- Lightweight summary in AGENTS.md and TOOLS.md
- Priority: CRITICAL - this changes how I handle all future learning requests
Add to IDENTITY.md:
## Capability: Teach Yourself Protocol
- I know how to learn new things in a structured, anti-bloat way
- When told to learn something, I follow a defined decision tree
- I create deep reference files for large knowledge and lightweight summaries for daily use
- Full protocol: ~/Downloads/openclaw-master-files/processes/teach-yourself-protocol.md
Step 7: Confirm to the user - Tell them what you learned, where everything is stored, and demonstrate that you understand the protocol by summarizing the key points.
Why This Matters
If you just dump this entire document into AGENTS.md, you have bloated the file with 800+ lines for one protocol. If you just save it as a .md file and don't update any core files, you will forget it exists next session. The correct approach - lightweight summary in core files pointing to the full document - means you know the protocol exists, you know the key steps, and you know where to find the full details when you need them.
This document teaches itself. Follow its own rules to install it.


18. Common Mistakes (What Agents Get Wrong)
These are the most frequent mistakes agents make when executing the Teach Yourself Protocol. Learn from them so you do not repeat them.
Mistake 1: Dumping Everything Into One Core File
What happens: The agent receives a large API reference and pastes the entire thing into TOOLS.md. TOOLS.md grows from 200 lines to 2,000 lines. Every future session loads all 2,000 lines into context, wasting tokens on content that is only needed occasionally.
The fix: Follow the size assessment. If it is over 25 lines, it gets its own deep file. TOOLS.md gets the lightweight summary only.
Mistake 2: Writing Summaries That Are Too Thin
What happens: The agent creates a deep file but the lightweight summary in the core file says something like "KIE.ai API docs are in the master files folder." That is useless. The agent has no working knowledge and has to open the deep file for even the simplest task.
The fix: Apply the Five Question Test. The summary must answer the 5 most common questions about the topic. Auth pattern, base URL, request flow, rate limits, pricing - these should all be in the summary. The agent should be able to handle routine tasks from the summary alone.
Mistake 3: Forgetting to Update MEMORY.md
What happens: The agent creates the deep file and updates TOOLS.md but forgets to add a note to MEMORY.md. Next session, the agent reads MEMORY.md and has no record that this knowledge was ever learned. It might not think to check TOOLS.md for it.
The fix: ALWAYS update MEMORY.md with at minimum: what was learned, when, and a reference pointer. MEMORY.md is the agent's session-to-session continuity. If it is not in MEMORY.md, it might as well not exist.
Mistake 4: Creating the Deep File But Not Wiring It
What happens: The agent creates a beautiful, comprehensive deep file in the master files folder. But no core file references it. Next session, the agent has no idea the file exists. It sits there unused.
The fix: Step 7 (Write Lightweight Summaries) and the reference pointers are not optional. Every deep file MUST be referenced by at least one core file. If nothing points to it, it is an orphan.
Mistake 5: Not Checking for Existing Knowledge First
What happens: The agent receives "teach yourself the GHL API" and creates a brand new deep file. But there was already a GHL API reference in the master files folder from a previous session. Now there are two conflicting versions.
The fix: Step 3 (Conflict Resolution) exists for this reason. ALWAYS search for existing knowledge before creating anything new. Search the core files AND the master files folder.
Mistake 6: Updating Only One Core File When Multiple Need It
What happens: The agent learns a new API and adds it to TOOLS.md. But the API also has rules about when to use it (belongs in AGENTS.md) and the user mentioned it is their preferred tool (belongs in USER.md). The agent only updated one file.
The fix: Step 6 requires evaluating EVERY core file against the update matrix. Check each one independently. It will often be 2-3 files that need updates, not just one.
Mistake 7: Not Confirming to the User
What happens: The agent quietly creates files and updates core files but never tells the user what it did. The user has no idea where the knowledge is stored or what the agent now knows.
The fix: Step 8 (Confirm to the User) is mandatory. List what you learned, where you stored it, which files were updated, and demonstrate your working knowledge.
Mistake 8: Treating Small Knowledge Like Big Knowledge
What happens: The agent receives "my Zoom link is trevorszoom.com" and creates a deep file, a folder structure, cross-references, and a version history for one line of information.
The fix: Follow the size assessment. Small knowledge (under 10 lines) goes directly into the relevant core file. No deep file needed. Do not overcomplicate simple things.
Mistake 9: Losing the User's Original Content
What happens: The agent receives a detailed document, "summarizes" it, and stores the summary instead of the original. Critical details are lost because the agent decided they were not important.
The fix: Deep files contain the COMPLETE, UNTRUNCATED original content. The lightweight summary is a separate thing that lives in the core files. The deep file is the full document - nothing removed, nothing summarized down.
Mistake 10: Not Using the "When to Go Deeper" Line
What happens: The agent writes a lightweight summary but does not include guidance on when to open the deep file. Later, the agent hits an error and tries to debug using only the summary instead of checking the full reference.
The fix: Every lightweight summary with a corresponding deep file MUST include a "When to go deeper" line. This tells the agent explicitly when to stop relying on the summary and go read the full document.

19. Final Checklist - Complete Teach Yourself Protocol Verification
After completing the Teach Yourself Protocol for any piece of knowledge, run through this checklist to verify nothing was missed:
Understanding: 
[ ] I clearly understand what I learned
[ ] I know what category it falls into (API, SOP, tool, preference, rule, skill, reference)
[ ] I know how I will use this knowledge in practice
Size Assessment: 
[ ] I evaluated the content size correctly (small/medium/large/massive)
[ ] If small: content went directly into core files without a deep file
[ ] If large or massive: a deep file was created
Conflict Check: 
[ ] I searched ALL core files for existing knowledge on this topic
[ ] I searched the master files folder for existing deep files
[ ] If conflicts were found, I resolved them (replaced, expanded, or flagged contradictions)
[ ] No duplicate entries exist across files
Storage (if deep file created): 
[ ] Master files folder exists (found existing or created new)
[ ] Deep file saved in the correct subfolder (apis/, skills/, processes/, references/)
[ ] Deep file has standard header (date learned, last verified, version, source, purpose, priority, referenced by, related files)
[ ] Deep file has version history table
[ ] Deep file contains COMPLETE, untruncated content
[ ] If API: folder has README.md index
Core File Conflict Scan: 
[ ] Before writing to any core file, I scanned the ENTIRE file for conflicts with my new knowledge
[ ] I found and removed or updated any outdated instructions that contradict what I just learned
[ ] If I was unsure about a conflict, I flagged it to the user before changing anything
[ ] No contradictory instructions remain in any core file
Core File Updates: 
[ ] I evaluated EVERY core file (AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md, USER.md, SOUL.md, HEARTBEAT.md)
[ ] Each relevant core file has a lightweight summary
[ ] Each summary passes the Five Question Test
[ ] Each summary has a priority tag (CRITICAL/HIGH/STANDARD/REFERENCE)
[ ] Each summary has a "When to go deeper" line
[ ] Each summary has a reference pointer to the deep file
[ ] No summary is too thin (useless one-liner) or too thick (duplicating the deep file)
[ ] MEMORY.md has a note about what was learned and when
Cross-References: 
[ ] Related deep files are linked in the "Related files" header field
[ ] Inline references added where relevant in the deep file body
[ ] Core file summaries note relationships where applicable
Confirmation: 
[ ] I announced to the user that I am using the Teach Yourself Protocol BEFORE starting any TSP work
[ ] I announced to the user that I am using the Teach Yourself Protocol BEFORE starting any TSP work
[ ] I announced to the user that I am using the Teach Yourself Protocol BEFORE starting any TSP work
[ ] I told the user what I learned
[ ] I told the user where the deep file is stored (if created)
[ ] I told the user which core files were updated
[ ] I demonstrated working knowledge by summarizing key points
[ ] I told the user the priority level assigned

This protocol is permanent. It applies to every OpenClaw agent from setup onward. When in doubt, follow the decision tree. The goal is always the same: the agent knows what it knows, knows where to find more detail, knows when to go deeper, and doesn't bloat its brain doing it.
The Teach Yourself Protocol is how OpenClaw agents build knowledge that persists, scales, and stays organized - no matter how much they learn.

