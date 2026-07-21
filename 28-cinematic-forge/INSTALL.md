# Cinematic Forge - Installation Instructions

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


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
   3) `INSTRUCTIONS.md` and `EXAMPLES.md` (and any `*-full.md`) (if present)
   4) Any other `.md` files (if present)
   5) `CORE_UPDATES.md`

Conflict rule:
- If any generic wrapper guidance conflicts with this skill folder, this skill folder wins.


## What This Is

Cinematic Forge is an AI video production skill that takes a user from concept to finished, uploaded video. It handles intake, storyboarding, AI image generation, AI video generation, AI audio production (voice, music, sound effects), FFmpeg assembly, media library upload, and revision cycles.

## Prerequisites

### 1. Teach Yourself Protocol (MANDATORY)

The agent MUST know the Teach Yourself Protocol before it can learn Cinematic Forge. If the agent does not know TYP:

1. Install the `teach-yourself-protocol` skill first (see its INSTALL.md)
2. Have the agent learn it by saying "Teach yourself this" and providing the full protocol document
3. Verify the agent knows TYP before proceeding

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

The agent needs access to these services. API keys should be stored in the agent's secrets file — `~/.openclaw/secrets/.env` on Mac, `/data/.openclaw/secrets/.env` on a VPS:

| Service | What For | How to Get |
|---------|----------|------------|
| **KIE.ai** | Video, image, voice, music, SFX generation | https://kie.ai/api-key |
| **GHL/Convert and Flow** | Media library upload (preferred) | Private Integration Token (PIT) from GHL settings |
| **imgBB** (optional) | REFERENCE IMAGES ONLY — still images and animated GIFs; it cannot host the final MP4 | https://api.imgbb.com/ - create free account |

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

### Step 1: Confirm the skill is installed in the right place

1. Open Terminal.
2. Run:

```bash
# Mac
ls -la ~/.openclaw/skills/28-cinematic-forge/
# VPS
ls -la /data/.openclaw/skills/28-cinematic-forge/
```

3. You should see files like `SKILL.md`, `INSTALL.md`, `README.md`, `CORE_UPDATES.md`, `qc-cinematic-forge.sh` and `qc-output.sh`.

**The directory name is `28-cinematic-forge`, with the numeric prefix, everywhere.**
That is the name in the repository, the name SKILL.md's Phase 0 resolves
(`$SKILL_DIR`), and the name this document and QC.md use. An install performed
into an unprefixed `cinematic-forge/` puts the skill where the runtime does not
look for its helper scripts.

If you do not see that folder, re-run the onboarding installer for this package so the skill is copied into `~/.openclaw/skills/`.

### Step 2: Teach the agent the skill

1. In chat with your agent, say:

> Teach yourself this skill

2. Paste the full contents of `~/.openclaw/skills/28-cinematic-forge/SKILL.md`.

The agent should follow Teach Yourself Protocol (TYP): discover all `.md` files in the folder, read them, then summarize pointers into the allowed core files.

### Step 3: Apply the core file updates (mandatory)

Apply the updates in `CORE_UPDATES.md`.

Rules:
- Update ONLY the core files listed in `CORE_UPDATES.md`.
- Do NOT paste large documentation into core files. Add short pointers only.

### Step 4: Verify API access

Verify the required API keys are present.

Minimum expectation:
- KIE.ai key is present and you can access VEO, Nano Banana Pro, ElevenLabs, and Suno via KIE.ai

**Dependencies for the delivery gate.** `qc-output.sh`'s technical mode needs
`ffmpeg`/`ffprobe` only. Its DELIVERY mode additionally needs `jq` (it reads the
delivery-requirements record, the post-production receipts and the upload
response as structured data) and `curl` (it downloads the hosted object). A
missing dependency is reported and exits non-zero — the gate never skips a check
and reports a pass.

### Step 5: Test with a simple video

Try a quick test:

- Create a short 15 second test video: a person walking on a beach at sunset

The agent should:
1. Start the 14-question intake (one question at a time)
2. For a test, you can answer quickly
3. Assemble the final output and return the deliverable

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
- Fallback for the FINAL VIDEO: a video-capable store the client controls — their
  own object storage or CDN (S3/R2/GCS behind a CDN), their site's media library,
  or a video host they own. Verify it the same way: the store's upload response
  must carry an asset identifier and a URL bound to it, and
  `qc-output.sh --upload-response …` must download and probe the hosted object.
- **NOT imgBB.** imgBB is a REFERENCE-IMAGE host: it serves still images and
  animated GIFs and will not host an MP4. The fallback is reached exactly when
  the primary path failed, so naming a host that cannot serve the artifact either
  fails or produces a link that is not the video.

**Agent skips the Teach Yourself Protocol prerequisite:**
- This is a hard requirement - Cinematic Forge references TYP concepts throughout
- Install TYP first, then re-teach Cinematic Forge

## Agent Model Requirements

The agent executing Cinematic Forge MUST be a model that supports tool calls (API requests, file operations, etc.):

**Recommended (client-available, Ollama Cloud first — never Anthropic):** `ollama/deepseek-v4-pro:cloud` or `ollama/minimax-m3:cloud` (primary), `openrouter/deepseek/deepseek-v4-pro` (fallback for clients with OpenRouter), GPT-5.2
**BANNED:** Kimi K2.5 (cannot make tool calls); Anthropic models (operator-only, cost-prohibitive for clients)

## Important Notes

- **9:16 vertical is ALWAYS the primary format.** 16:9 is only created after 9:16 is approved.
- **No Topaz upscale until the user approves the draft.** Don't waste processing on unapproved content.
- **Narrator and character dialogue NEVER overlap** in the same segment.
- **All VEO audio is discarded** and replaced with ElevenLabs + Suno audio layers.
- **GHL uses Private Integration Tokens (PIT)**, not API keys. Use the correct terminology.

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
