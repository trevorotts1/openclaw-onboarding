# FINAL INSTRUCTIONS FOR AI AGENT - PROFESSIONAL B-ROLL VIDEO EDITING

Your goal is to transform a talking-head video into a professionally edited video where the person appears only at key moments, with B-roll filling the rest. The person's voice continues throughout as voiceover.

---

## THE GOAL

**Transform:** Video of person talking continuously  
**Into:** Professional video with person visible only at beginning, middle, and end - B-roll fills everything else.

**Professional Structure:**
- **Beginning (8-10 sec):** Person visible - hook/intro
- **Section 1 (20-30 sec):** B-roll only (person's voice as voiceover)
- **Middle (8-10 sec):** Person visible - transition/key point
- **Section 2 (20-30 sec):** B-roll only (voice continues)
- **End (8-10 sec):** Person visible - closing/call-to-action

**Result:** Person appears roughly 25-50% of the time (see the worked examples below), B-roll fills the rest. Looks professionally produced.

---

## COMPLETE WORKFLOW

### STEP 1: Install Tools (If Needed)

```bash
pip install yt-dlp moviepy scenedetect opencv-python
```

Verify:
```bash
yt-dlp --version && python3 -c "import moviepy" && scenedetect --version
```

---

### STEP 2: Install Skill (If Needed)

```bash
The .skill file is an archive. No CLI command needed - install by following SKILL.md, INSTALL.md, and CORE_UPDATES.md instructions.
```

---

### STEP 3: DOWNLOAD THE CLIENT VIDEO

The client gives you a video link. **You download it:**

```bash
~/.openclaw/skills/video-editor/scripts/download.sh \
  --url "[VIDEO_URL]" \
  --output original_video.mp4
```

**NOTE: This is a 51-second test video.** See the 51-second structure example below.

---

### STEP 4: EXTRACT FULL AUDIO (For Voiceover)

**Extract the entire audio track - this becomes the voiceover:**

```bash
~/.openclaw/skills/video-editor/scripts/extract-audio.sh \
  --input original_video.mp4 \
  --output full_voiceover.aac
```

This audio plays continuously over B-roll and person segments.

---

### STEP 5: TRANSCRIBE TO UNDERSTAND CONTENT

```bash
whisper full_voiceover.aac --model medium --output_format json --output_dir /tmp
```

**Read the transcript.** Understand:
- What topics are discussed
- Key themes for B-roll matching
- Emotional tone
- Specific visual references mentioned

---

### STEP 6: DETERMINE PERSON SEGMENTS

**Based on transcript, identify 3 key moments for person visibility:**

1. **Beginning (0:00-0:08 or 0:10):** Opening hook, introduction
2. **Middle (~30-40% mark):** Key transition point, important statement
3. **End (last 8-10 seconds):** Closing, call-to-action

**The person appears at these 3 points ONLY.**

---

### STEP 7: EXTRACT PERSON SEGMENTS

**Cut out the 3 segments where person will be visible:**

```bash
# Segment 1: Beginning (adjust timestamps based on content)
~/.openclaw/skills/video-editor/scripts/cut.sh \
  --input original_video.mp4 \
  --start 00:00:00 \
  --duration 8 \
  --output person_beginning.mp4

# Segment 2: Middle (find best moment from transcript)
~/.openclaw/skills/video-editor/scripts/cut.sh \
  --input original_video.mp4 \
  --start 00:00:45 \
  --duration 8 \
  --output person_middle.mp4

# Segment 3: End
~/.openclaw/skills/video-editor/scripts/cut.sh \
  --input original_video.mp4 \
  --start 00:01:50 \
  --duration 10 \
  --output person_end.mp4
```

---

### STEP 8: CREATE B-ROLL STORYBOARD FROM TRANSCRIPT

**Based on what the person says, create B-roll concepts:**

| Time Range | Transcript Content | B-roll Concept | Duration |
|------------|-------------------|----------------|----------|
| 0:08-0:45 | Topic A discussed | B-roll matching Topic A | 37 sec |
| 0:53-1:10 | Topic B discussed | B-roll matching Topic B | 37 sec |

**Break into 8-second B-roll clips:**
- You need ~8-10 B-roll clips total
- Each clip covers what they're saying in that section
- Visuals match the audio content

---

### STEP 9: GENERATE B-ROLL WITH KIE.AI (through Skill 67)

This skill has no KIE client. You generate the clips through **Skill 67 (`67-kie-video`)**, which owns model selection, payload validation, dispatch and QC, using the client's own KIE key. Rules for endpoints, rate limit, credit preflight and saving results live in `07-kie-setup/references/kie-common-rules.md`.

**Choose the model with Skill 67's selector, never from memory or from a price list:**

```bash
python3 ~/.openclaw/skills/67-kie-video/scripts/select_video_model.py "8 second vertical B-roll: <what the clip shows>"
```

- If the client or the department names a model, that explicit pick wins.
- Get the price for the chosen model with `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>` (live `pricingDesc`; fallback snapshot `74-kie-live-adapter/references/kie-model-registry.json`). This skill holds no prices; do not quote one from memory.
- Announce provider, model and estimated USD for the whole batch and get approval before generating. Run the credit preflight from the rules file first.
- **Sora is prohibited** by the Video department. Never use or offer it.

**Example prompts based on transcript:**
- "Professional business team collaborating, modern office, natural lighting, cinematic, 8 seconds"
- "Abstract technology network visualization, blue tones, smooth animation, 8 seconds"
- "Urban cityscape sunrise, energetic mood, aerial view, 8 seconds"

**Generate 8-10 clips covering the full video length.** Save each finished clip to disk the moment it completes (KIE download URLs expire).

---

### STEP 10: BUILD THE FINAL VIDEO SEQUENCE

**Assemble in this order:**

1. Person beginning (8 sec)
2. B-roll clip 1 (8 sec)
3. B-roll clip 2 (8 sec)
4. B-roll clip 3 (8 sec)
5. ... (continue B-roll)
6. Person middle (8 sec)
7. B-roll clip 4 (8 sec)
8. B-roll clip 5 (8 sec)
9. ... (continue B-roll)
10. Person end (8-10 sec)

**Use MoviePy to assemble with continuous voiceover:**

```python
# Create Python script to assemble
from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeVideoClip, AudioFileClip

# Load clips
person_beginning = VideoFileClip("person_beginning.mp4")
broll_1 = VideoFileClip("broll_01.mp4")
broll_2 = VideoFileClip("broll_02.mp4")
# ... load all b-roll clips
person_middle = VideoFileClip("person_middle.mp4")
broll_3 = VideoFileClip("broll_03.mp4")
# ... more b-roll
person_end = VideoFileClip("person_end.mp4")

# Load voiceover audio
voiceover = AudioFileClip("full_voiceover.aac")

# Concatenate video clips
video_sequence = concatenate_videoclips([
    person_beginning,
    broll_1, broll_2, broll_3,  # as many as needed
    person_middle,
    broll_4, broll_5, broll_6,  # as many as needed
    person_end
], method="compose")

# Apply continuous voiceover
final_video = video_sequence.set_audio(voiceover)

# Write output
final_video.write_videofile("client_professional_edit.mp4", codec='libx264', audio_codec='aac')
```

**Or use FFmpeg for faster processing:**

Create a concat list file:
```
file 'person_beginning.mp4'
file 'broll_01.mp4'
file 'broll_02.mp4'
file 'broll_03.mp4'
file 'person_middle.mp4'
file 'broll_04.mp4'
file 'broll_05.mp4'
file 'person_end.mp4'
```

Then:
```bash
ffmpeg -f concat -safe 0 -i concat_list.txt -i full_voiceover.aac \
  -c:v libx264 -c:a aac -shortest client_assembled.mp4
```

---

### STEP 11: ADD PROFESSIONAL TOUCHES

**Add captions:**
```bash
~/.openclaw/skills/video-editor/scripts/caption.sh \
  --input client_assembled.mp4 \
  --output client_with_captions.mp4
```

**Optional: Add subtle transitions between segments**
Use MoviePy for crossfades if needed for smoother flow.

---

### STEP 12: RESIZE FOR PLATFORM

```bash
# For TikTok/Reels (9:16 vertical)
~/.openclaw/skills/video-editor/scripts/resize.sh \
  --input client_with_captions.mp4 \
  --platform tiktok \
  --output client_final_tiktok.mp4

# For YouTube/LinkedIn (16:9)
~/.openclaw/skills/video-editor/scripts/resize.sh \
  --input client_with_captions.mp4 \
  --platform youtube \
  --output client_final_youtube.mp4
```

---

## KEY PRINCIPLES FOR PROFESSIONAL LOOK

### 1. Continuous Voiceover
- Person's voice NEVER stops
- Plays over both B-roll AND person segments
- Creates seamless professional feel

### 2. Strategic Person Placement
- **Beginning:** Hook viewers with your presence
- **Middle:** Reconnect at key transition
- **End:** Personal close with call-to-action

### 3. B-roll Matches Content
- Visuals correspond to what's being said
- Maintains viewer engagement
- Professional documentary style

### 4. Smooth Transitions
- Simple cuts work best
- Optional subtle crossfades
- Consistent pacing

---

## B-ROLL GENERATION WITH KIE.AI

**For each 8-second clip:**

1. **Identify what person is saying** in that time segment
2. **Create visual concept** that illustrates the point
3. **Generate through Skill 67** (see STEP 9 for model choice, pricing and approval):
   - Model: the one Skill 67's selector returns (or the one the client named)
   - Duration: 8 seconds, if the chosen model supports it (check with `python3 74-kie-live-adapter/scripts/kie_live_adapter.py validate` or Skill 67's registry)
   - Prompt: Descriptive, matches content theme

**Example workflow:**
- Person talks about business growth → B-roll: Charts, cityscapes, success imagery
- Person talks about technology → B-roll: Tech visuals, innovation scenes
- Person talks about motivation → B-roll: Inspirational scenes, achievement moments

---

## VIDEO STRUCTURE EXAMPLE (51-Second Video - CLIENT TEST)

```
00:00-00:08  PERSON VISIBLE (8 sec) - Hook/Intro
00:08-00:16  B-ROLL 1 (8 sec) - Supports first point
00:16-00:24  B-ROLL 2 (8 sec) - Continues first point
00:24-00:32  PERSON VISIBLE (8 sec) - Middle/Key transition
00:32-00:40  B-ROLL 3 (8 sec) - Supports second point
00:40-00:43  B-ROLL 4 (3 sec) - Transition to close
00:43-00:51  PERSON VISIBLE (8 sec) - Closing/CTA
```

**Total:** 51 seconds  
**Person visible:** 24 seconds (~47%)  
**B-roll:** 27 seconds (~53%)

**For this 51-second video, you need:**
- 4 B-roll clips (8 sec, 8 sec, 8 sec, 3 sec)
- 3 person segments extracted from original
- Continuous voiceover throughout

---

## VIDEO STRUCTURE EXAMPLE (64-Second Video)

```
00:00-00:08  PERSON VISIBLE (8 sec) - Hook/Intro
00:08-00:16  B-ROLL 1 (8 sec) - Supports first point
00:16-00:24  B-ROLL 2 (8 sec) - Continues first point
00:24-00:32  B-ROLL 3 (8 sec) - Transition visuals
00:32-00:40  PERSON VISIBLE (8 sec) - Middle/Key point
00:40-00:48  B-ROLL 4 (8 sec) - Supports second point
00:48-00:56  B-ROLL 5 (8 sec) - Continues second point
00:56-01:04  PERSON VISIBLE (8 sec) - Closing/CTA
```

**Total:** 64 seconds  
**Person visible:** 24 seconds (~38%)  
**B-roll:** 40 seconds (~62%)

Adjust ratios based on content and preference.

---

## COMPLETE COMMAND SEQUENCE

```bash
# 1. Download
~/.openclaw/skills/video-editor/scripts/download.sh --url "URL" --output original.mp4

# 2. Extract full audio for voiceover
~/.openclaw/skills/video-editor/scripts/extract-audio.sh --input original.mp4 --output voiceover.aac

# 3. Transcribe for content analysis
whisper voiceover.aac --model medium --output_format json --output_dir /tmp

# YOU: Analyze transcript, determine 3 person segments

# 4. Extract person segments (adjust timestamps)
~/.openclaw/skills/video-editor/scripts/cut.sh --input original.mp4 --start 00:00:00 --duration 8 --output person_beginning.mp4
~/.openclaw/skills/video-editor/scripts/cut.sh --input original.mp4 --start 00:00:45 --duration 8 --output person_middle.mp4
~/.openclaw/skills/video-editor/scripts/cut.sh --input original.mp4 --start 00:01:50 --duration 10 --output person_end.mp4

# YOU: Create B-roll storyboard from transcript

# 5. Generate B-roll through Skill 67 (you do this step - generate 8-10 clips)
# Result: broll_01.mp4 through broll_10.mp4

# 6. Assemble final video (use Python script or FFmpeg concat)
# Apply voiceover.aac as continuous audio

# 7. Add captions
~/.openclaw/skills/video-editor/scripts/caption.sh --input assembled.mp4 --output captioned.mp4

# 8. Resize for platform
~/.openclaw/skills/video-editor/scripts/resize.sh --input captioned.mp4 --platform tiktok --output final.mp4

## REMEMBER THE STRUCTURE

**Person visible:** Only at 3 points (beginning, middle, end)  
**B-roll:** Fills everything else  
**Voiceover:** Continuous throughout (person's voice never stops)  
**Result:** Professional documentary-style video

**YOU do ALL the work.** The client just gives you the video link. You analyze, extract, generate B-roll, assemble, and deliver.

**Ready to create a professional B-roll cut!**
---

## 🔴 KIE.AI GENERATION ERROR HANDLING

KIE errors, retries, rate limits and credit problems are handled by the canonical rules in `07-kie-setup/references/kie-common-rules.md` and by Skill 67's dispatch and QC steps. Follow those. Do not use status-code advice from memory.

What this skill adds on top, for B-roll batches:

- Retry only the single clip that failed, never the whole batch.
- Credit and key problems (unauthorized, forbidden, insufficient credits) are not retried. Stop and report them once. The key is the client's own; never print it and never swap in another key.
- If a clip still fails after Skill 67's retry ladder, skip it and note it in your final report.
- Save every finished clip to disk immediately, before generating the next one.

**Report to user:**
"B-roll clip [number] failed to generate. Error: [message]. All other clips completed. You can regenerate that clip manually or I can retry it now."

**Never deliver a video with a missing B-roll slot without telling the user.**

---

## 🔴 TIMESTAMP VALIDATION BEFORE MERGE

Before running any merge or assembly script, validate all timestamps:

```bash
# Check video duration first
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 original.mp4
```

Then verify each timestamp is within the video duration:
- Start time must be less than total duration
- Start time + clip duration must not exceed total duration
- All timestamps must be in HH:MM:SS format

**If a timestamp is out of range:**
1. Do NOT run the merge script
2. Recalculate the correct timestamps from the transcript
3. Confirm the corrected timestamps before proceeding

**A timestamp error caught before assembly saves 10+ minutes of wasted processing.**
