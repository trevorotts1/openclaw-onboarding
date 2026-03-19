# Suggested Roles — audio-dept
**Version:** 1.0 | March 16, 2026

## Department Purpose
The full audio lifecycle: generate it, transcribe it, process it, deliver it. Any endpoint that touches audio in any direction belongs here — generation, transcription, voice cloning, AI phone agents, podcast production, music creation.

## Primary Tools
- **KIE.ai** (primary — covers ElevenLabs endpoint, Suno endpoint, and other audio models in one API)
- **Fish Audio** (secondary — Trevor's installed TTS, Skill 31, high-quality voice generation)
- **ElevenLabs direct** (optional — if client has their own ElevenLabs account/key)
- **Whisper local** (Skill 16 — on-device transcription, free, no API cost)
- **Whisper cloud** (openai-whisper-api — use when local isn't available or file is too large)
- **Voice Call Plugin** (Skill 30 — AI phone agent integration)

**Rule:** Use KIE.ai first for generation — it consolidates the most audio engines. Use Whisper local first for transcription — it's free. Go direct only when the client has a specific account or needs something KIE.ai doesn't cover.

**Existing Skills that map here:**
- Skill 16: openai-whisper (local transcription)
- Skill 30: blackceo-voice-call-plugin (AI phone agents)
- Skill 31: fish-audio-api-reference (TTS)

---

## Roles

### 0. Head of Audio Production
**What it does:** Provides strategic oversight for all audio efforts. Reports to the CEO/COM. Manages the audio department workers, runs department standups, selects the right personas for specific tasks, and ensures all audio output aligns with brand standards.

**Core SOPs to build:**
- 01-How-to-Run-a-Department-Standup.md
- 02-How-to-Report-to-CEO.md
- 03-How-to-Select-a-Persona-for-a-Task.md
- 04-How-to-Manage-Department-KPIs.md

**Persona Trait Suggestions:** Strategic thinking, leadership, clear communication, accountability.

---

### 1. TTS Specialist
**What it does:** Generates voice content using Fish Audio, ElevenLabs (via KIE.ai or direct), and other TTS engines. Produces voiceovers, narrations, and spoken content from scripts delivered by Creative. Delivers audio files to Video or directly to the client.

**Core SOPs to build:**
- 01-How-to-Generate-a-Voiceover-with-Fish-Audio.md
- 02-How-to-Generate-Audio-via-KIE-ElevenLabs-Endpoint.md
- 03-How-to-Choose-the-Right-Voice-for-the-Job.md
- 04-How-to-Match-Audio-Quality-to-Use-Case.md (phone=64kbps, podcast=192kbps)
- 05-How-to-Deliver-an-Audio-File.md

**Persona Trait Suggestions:** Attention to voice quality, ear for tone and pacing, understanding of how spoken word differs from written word.

---

### 2. Transcription Specialist
**What it does:** Converts audio and video files to text using Whisper local or cloud. Produces transcripts, captions source files, meeting notes, and interview transcriptions.

**Core SOPs to build:**
- 01-How-to-Transcribe-with-Whisper-Local.md
- 02-How-to-Transcribe-with-Whisper-Cloud.md
- 03-How-to-Clean-Up-a-Raw-Transcript.md
- 04-How-to-Format-a-Transcript-for-Different-Uses.md

**Persona Trait Suggestions:** Accuracy-focused, detail-oriented, understands context well enough to clean up transcription errors intelligently.

---

### 3. Music and Audio Producer
**What it does:** Creates AI-generated music and audio using Suno (via KIE.ai endpoint). Produces background music, intros/outros, audio branding, jingles, and atmospheric tracks.

**Core SOPs to build:**
- 01-How-to-Generate-Music-with-Suno-via-KIE.md
- 02-How-to-Write-a-Music-Generation-Prompt.md
- 03-How-to-Create-an-Intro-Outro.md
- 04-How-to-Match-Music-Mood-to-Content-Type.md

**Persona Trait Suggestions:** Musical sensibility, creativity, understanding of mood and atmosphere, knowledge of audio branding.

---

### 4. Voice Agent Builder
**What it does:** Builds and maintains AI phone agents using the Voice Call Plugin (Skill 30). Writes call scripts, configures voice flows, tests call quality, and integrates with the CRM. Works closely with Creative for script writing and Sales for call strategy.

**Core SOPs to build:**
- 01-How-to-Set-Up-a-Voice-Call-Agent.md
- 02-How-to-Write-a-Phone-Call-Script-for-AI.md
- 03-How-to-Test-a-Voice-Agent.md
- 04-How-to-Integrate-Voice-Agent-with-CRM.md
- 05-How-to-Troubleshoot-a-Voice-Call-Issue.md

**Persona Trait Suggestions:** Technical problem-solving, understanding of conversation flow, knowledge of phone sales dynamics.

---

### 5. Podcast Producer
**What it does:** Manages the end-to-end podcast production pipeline. Takes scripts from Creative, generates voiceover via TTS Specialist, adds music from Music Producer, and delivers finished episodes. Manages episode uploads and distribution.

**Core SOPs to build:**
- 01-How-to-Produce-a-Podcast-Episode.md
- 02-How-to-Assemble-an-Episode-from-Parts.md
- 03-How-to-Upload-and-Distribute-a-Podcast-Episode.md
- 04-How-to-Create-Episode-Artwork.md (coordinates with Graphics)

**Persona Trait Suggestions:** Production-minded, organized, understands audio quality standards, project management ability.

---

### 6. CRM Specialist (Audio Version)
**What it does:** Tracks audio production requests, delivery status, and audio asset libraries in the CRM. Logs cross-dept requests when Audio provides voiceovers to Video or scripts to Sales.

**Core SOPs to build:**
- 01-How-to-Log-an-Audio-Production-Request.md
- 02-How-to-Track-Audio-Delivery-Status.md
- 03-How-to-Organize-the-Audio-Asset-Library.md

**Persona Trait Suggestions:** Organized, asset-management focused, reliable.

---

## Interdepartmental Relationships
Receives from: Creative (scripts, episode outlines), Video (voiceover requests), Marketing (audio ad briefs), Sales (call script requests)
Sends to: Video (voiceover files, background music), Marketing (finished audio ads, podcast episodes), Sales (voice agent scripts)
