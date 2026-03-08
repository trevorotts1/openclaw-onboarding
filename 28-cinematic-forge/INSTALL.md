# Cinematic Forge - Installation Instructions

## Teach Yourself Protocol (TYP) - Mandatory Read Order

Before you run any commands in this skill:

1. Discover every Markdown file in this skill folder (including subfolders):
   ```bash
   cd "$(dirname "$0")" 2>/dev/null || true
   find . -name "*.md" | sort
   ```
2. Read every discovered `.md` file.
3. Use this read order:
   1) `SKILL.md`
   2) `INSTALL.md`
   3) `INSTRUCTIONS.md` and `EXAMPLES.md` (and any `*-full.md`)
   4) `CORE_UPDATES.md`

Conflict rule:
- If any generic wrapper guidance conflicts with this skill folder, this skill folder wins.


## What This Is

Cinematic Forge is an AI video production skill that takes a user from concept to finished, uploaded video. It handles intake, storyboarding, AI image generation, AI video generation, AI audio production (voice, music, sound effects), FFmpeg assembly, media library upload, and revision cycles.

## Prerequisites

### 1. Teach Yourself Protocol (MANDATORY)

The agent MUST know the Teach Yourself Protocol before it can learn Cinematic Forge. If the agent doesn't know TSP:

1. Install the `teach-yourself-protocol` skill first (see its INSTALL.md)
2. Have the agent learn it by saying "Teach yourself this" and providing the full protocol document
3. Verify the agent knows TSP before proceeding

### 2. Required Tools

Check that these are installed on the system:

```bash
# FFmpeg (video processing)
ffmpeg -version

# curl (API calls)
curl --version
```

If FFmpeg is not installed:
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### 3. Required API Access

The agent needs access to these services. API keys should be stored in the agent's secrets/environment file (e.g., `~/clawd/secrets/.env` or equivalent):

| Service | What For | How to Get |
|---------|----------|------------|
| **KIE.ai** | Video, image, voice, music, SFX generation | https://kie.ai/api-key |
| **GHL/Convert and Flow** | Media library upload (preferred) | Private Integration Token (PIT) from GHL settings |
| **imgBB** (fallback) | Image/media hosting if no GHL | https://api.imgbb.com/ - create free account |

**Important:** GHL/Convert and Flow does NOT use "API keys" - the correct term is **Private Integration Token (PIT)**. The agent should use this terminology with users.

### 4. Required Models via KIE.ai

These models must be available on the KIE.ai account:

| Model | Purpose | Approx Cost |
|-------|---------|-------------|
| VEO 3.1 Fast (`veo3_fast`) | Video generation | $0.40/segment |
| Nano Banana Pro | Image generation | ~$0.10/image |
| ElevenLabs Multilingual v2 (`eleven_multilingual_v2`) | Voice/dialogue | ~$0.10-0.30/clip |
| ElevenLabs Sound Effects (`eleven_sound_effects`) | SFX | ~$0.10/clip |
| Suno v4 (`suno_v4`) | Music generation | ~$0.20-0.50/track |

## Installation Steps

### Step 1: Find the Master Files Folder

Search `~/Downloads/` for the master files folder. It may be named:
- `openclaw-master-files`
- `openclaw-master-docs`
- or similar

If it doesn't exist, create it:
```bash
mkdir -p ~/Downloads/openclaw-master-files
```

### Step 2: Place the Skill Files

Copy the entire `cinematic-forge/` folder into the master files folder:

```
~/Downloads/[MASTER_FILES_PATH]/cinematic-forge/
  SKILL.md          (complete skill reference - intake, production, assembly)
  INSTALL.md        (this file)
  README.md         (quick overview)
```

### Step 3: Teach the Agent

Say to your agent:

> "Teach yourself this skill"

Then provide the contents of `SKILL.md`.

The agent should (following TSP):
1. Announce it is activating the Teach Yourself Protocol
2. Recognize this as a HIGH priority skill
3. Store the deep file in the master files folder (it's already there from Step 2)
4. Write lightweight summaries in the core files (see exact text below)
5. Confirm what it learned

### Step 3a: Core File Updates (What Goes Where)

The Teach Yourself Protocol should handle this automatically, but in case the agent needs guidance, here is EXACTLY what should be added to each core file. If the agent writes something vague like "video skill in master files folder" - that's wrong. These are the minimum entries:

**Add to TOOLS.md:**
```
## Cinematic Forge - AI Video Production Skill [PRIORITY: HIGH]
- **What it does:** Takes a user from concept to finished, uploaded video through a 14-question intake, 
  AI video generation (VEO 3.1 Fast), AI audio (ElevenLabs + Suno), FFmpeg assembly, and media library upload
- **Triggers on:** "create a video," "make me a video," "produce a video," or any request to build a video from scratch
- **NOT for:** Editing existing videos (use video-editor skill), cutting/trimming clips, downloading YouTube videos
- **Tools used:** VEO 3.1 Fast (video), Nano Banana Pro (images), ElevenLabs (voice/SFX), Suno (music), FFmpeg (assembly)
- **API provider:** KIE.ai for all generation models. Auth: Bearer token.
- **Cost:** ~$8.50 for a 90-second video (12 segments x $0.40 + images + audio + music)
- **Key rules:**
  - Ask 14 intake questions ONE AT A TIME (never all at once)
  - Budget confirmation BEFORE spending any credits
  - Narrator and character dialogue NEVER overlap in same segment
  - All VEO audio is discarded - replaced with ElevenLabs + Suno
  - 9:16 vertical is always primary format
  - No Topaz upscale until user approves draft
  - Agent must support tool calls (MiniMax M2.5 OK, Kimi K2.5 BANNED)
- **Project folders:** ~/Downloads/cinematic-forge-projects/[project-name]/
- **Session recovery:** project-state.json in each project folder tracks progress
- **Companion skills:** video-frames (frame extraction), summarize (YouTube analysis) - install if missing
- **When to go deeper:** First time producing a video, hitting VEO errors, complex audio sync issues,
  user provides a reference video to analyze, debugging FFmpeg assembly
- **Full reference:** ~/Downloads/[MASTER_FILES_PATH]/cinematic-forge/SKILL.md
- **Last learned:** [DATE]
```

**Add to AGENTS.md:**
```
## Cinematic Forge - Video Production Rules [PRIORITY: HIGH]
- When a user asks to CREATE a video from scratch, use the Cinematic Forge skill
- ALWAYS ask the 14 intake questions one at a time - never dump all questions at once
- ALWAYS confirm the budget estimate and get user approval before generating anything
- ALWAYS check KIE.ai credit balance before starting production
- NEVER use Kimi K2.5 for this skill - it cannot make API calls. Use MiniMax M2.5 or similar.
- NEVER overlap narrator voiceover and character dialogue in the same segment
- NEVER use VEO to generate text or logos - all text overlays added in post-production via FFmpeg
- NEVER upscale with Topaz until the user has approved the draft video
- 9:16 vertical is ALWAYS the primary format. 16:9 only after 9:16 is approved.
- Update project-state.json after EVERY completed step for session recovery
- Send progress updates to user after each segment completes - never leave them waiting in silence
- If user provides a reference video (Q12), analyze it using video-frames + summarize skills.
  If those skills aren't installed, install them and use TSP to learn them.
- Full skill reference: ~/Downloads/[MASTER_FILES_PATH]/cinematic-forge/SKILL.md
```

**Add to MEMORY.md:**
```
## Cinematic Forge Skill - Learned [DATE]
- AI video production skill: concept to finished uploaded video
- 14-question intake (one at a time), VEO 3.1 Fast video gen, ElevenLabs audio, Suno music, FFmpeg assembly
- Stored at: ~/Downloads/[MASTER_FILES_PATH]/cinematic-forge/SKILL.md
- Lightweight summaries in TOOLS.md (usage reference) and AGENTS.md (production rules)
- Requires: KIE.ai API key, FFmpeg, GHL PIT or imgBB for media hosting
- Companion skills: video-frames, summarize (for Q12 reference video analysis)
- Priority: HIGH
```

**Add to IDENTITY.md:**
```
## Capability: Cinematic Forge (AI Video Production)
- I can produce complete videos from scratch using AI
- I walk users through a structured 14-question intake, generate all visual and audio assets,
  assemble with FFmpeg, and deliver to their media library
- Tools: VEO 3.1 Fast, Nano Banana Pro, ElevenLabs, Suno, FFmpeg
- Full skill reference: ~/Downloads/[MASTER_FILES_PATH]/cinematic-forge/SKILL.md
```

**Note:** Replace `[MASTER_FILES_PATH]` with the actual folder name on the system (e.g., `openclaw-master-files`). Replace `[DATE]` with the current date.

The agent should also scan each core file for conflicts before writing (per TSP Step 7). If there's an existing video-related entry that conflicts with Cinematic Forge, update it rather than creating a duplicate.

### Step 4: Verify API Access

Ask your agent to verify it has the required API keys:

> "Check if you have a KIE.ai API key and can access the VEO, Nano Banana Pro, ElevenLabs, and Suno models"

The agent should check its secrets/environment files and confirm access.

### Step 5: Test with a Simple Video

Try a quick test:

> "Create a short 15-second test video of a person walking on a beach at sunset"

The agent should:
1. Start the 11-question intake (one at a time)
2. For a test, you can give quick answers
3. Watch for: proper question sequencing, image generation, video generation, audio creation, FFmpeg assembly, media library upload

## Troubleshooting

**Agent doesn't ask questions one at a time:**
- Re-read SKILL.md - the intake rules are explicit about one question at a time
- Remind the agent: "Ask me ONE question at a time"

**Agent tries to use Kimi K2.5:**
- Kimi CANNOT make API calls (no tool calls)
- Switch to MiniMax M2.5 or another model that supports tool calls

**VEO returns errors:**
- Check KIE.ai credit balance
- Verify API key is correct
- Check rate limits (20 req/10 sec max)

**Audio doesn't sync with video:**
- Use FFmpeg's `-itsoffset` flag to adjust audio timing
- Check that audio clip durations match their target segments

**GHL upload fails:**
- Verify the Private Integration Token (PIT) is valid
- Check that the PIT has media upload permissions
- Fallback: use imgBB for hosting

**Agent skips the Teach Yourself Protocol prerequisite:**
- This is a hard requirement - Cinematic Forge references TSP concepts throughout
- Install TSP first, then re-teach Cinematic Forge

## Agent Model Requirements

The agent executing Cinematic Forge MUST be a model that supports tool calls (API requests, file operations, etc.):

**Recommended:** MiniMax M2.5, Claude Opus/Sonnet, GPT-5.2
**BANNED:** Kimi K2.5 (cannot make tool calls)

## Important Notes

- **9:16 vertical is ALWAYS the primary format.** 16:9 is only created after 9:16 is approved.
- **No Topaz upscale until the user approves the draft.** Don't waste processing on unapproved content.
- **Narrator and character dialogue NEVER overlap** in the same segment.
- **All VEO audio is discarded** and replaced with ElevenLabs + Suno audio layers.
- **GHL uses Private Integration Tokens (PIT)**, not API keys. Use the correct terminology.
