# Video Creator Skill - Complete Instructions

## What This Skill Is

The **Video Creator Skill** generates videos from scratch using AI. Text-to-video, script-to-video, image animation, and multi-clip assembly with transitions and music.

**Purpose:** Create professional videos without filming anything. Turn ideas, scripts, or images into polished video content.

---

## What It Does

1. **Text-to-Video** - AI generates video from text descriptions
2. **Script-to-Video** - Converts written scripts into video scenes
3. **Image-to-Video** - Animates still images (Ken Burns, pan, zoom)
4. **Multi-Clip Assembly** - Combines clips with smooth transitions
5. **AI Avatar** - Creates presenter-style videos with virtual hosts
6. **Background Music** - Adds and mixes audio tracks
7. **Template Library** - 5 pre-built templates for common formats

---

## How to Install

### Step 1: Install Dependencies
```bash
pip install moviepy opencv-python requests pillow
```

### Step 2: Install the Skill
```bash
The .skill file is an archive. No CLI command needed - install by following SKILL.md, INSTALL.md, and CORE_UPDATES.md instructions.
```

Or manually:
```bash
unzip video-creator.skill -d $HOME/.openclaw/skills/
chmod +x $HOME/.openclaw/skills/video-creator/scripts/*.py
```

### Step 3: Configure AI Providers
```bash
# Set your API keys in environment
export KIE_API_KEY="your_key_here"
export RUNWAY_API_KEY="your_key_here"  # Optional
```

---

## How to Run (Real CLI Signatures)

### Text to Video

```bash
python3 scripts/text_to_video.py "A serene mountain landscape at sunset, cinematic" \
  --duration 8 \
  --style cinematic \
  --output mountain.mp4
```

Positional argument: `prompt` (the text description, in quotes).
Options: `--duration`, `--resolution` (720p/1080p/4k), `--provider` (kieai/runway/pika/mock), `--style` (cinematic/animated/realistic/abstract), `--output`, `--seed`, `--negative-prompt`.

### Script to Video

```bash
python3 scripts/script_to_video.py script.txt \
  --template tutorial \
  --output video.mp4
```

Positional argument: `script` (path to the script file).
Options: `--output`, `--provider`, `--quality` (social/web/broadcast/cinema), `--template`, `--chapters`.

### Image to Video

```bash
python3 scripts/image_to_video.py photo.jpg \
  --motion ken_burns \
  --duration 5 \
  --output animated.mp4
```

Positional argument: `image` (path to image file).
Options: `--output`, `--motion` (zoom/ken_burns/pan_left/pan_right/pan_up/pan_down/none), `--duration`, `--resolution`, `--zoom-direction` (in/out), `--music`, `--provider`.

### Add Music

```bash
python3 scripts/add_music.py video.mp4 \
  --music background.mp3 \
  --output final.mp4
```

Positional argument: `video` (path to video file).
Subcommands: `extract` (extract audio), `remove` (strip audio), `mix` (mix tracks).
Options: `--music`, `--genre` (upbeat/corporate/calm/epic/lofi/inspirational/tense), `--volume`, `--fade-in`, `--fade-out`, `--voiceover`, `--voice-volume`, `--output`, `--no-loop`.

### Multi-Clip Assembly

```bash
python3 scripts/multi_clip_assembly.py clip1.mp4 clip2.mp4 clip3.mp4 \
  --transition fade \
  --output assembled.mp4
```

Positional argument: `clips` (one or more video files).
Options: `--transition` (fade/slide_left/slide_right/slide_up/slide_down/wipe/zoom_in/zoom_out/none), `--transition-duration`, `--duration`, `--music`, `--output`, `--resolution`, `--fps`.

---

Apply the core file updates from `CORE_UPDATES.md`.
## Video Creator Skill
- Installed at: ~/.openclaw/skills/video-creator/
- Full reference: ~/.openclaw/skills/video-creator/SKILL.md
```

---

## For Clients/Customers

### What You Can Do

**"Create professional videos without a camera, without actors, without a studio."**

**Use Cases:**
- **Product demos** - "Show my product in action without filming"
- **Social media content** - "Create 30 TikTok videos from my blog posts"
- **Training videos** - "Turn my written SOPs into video tutorials"
- **Marketing campaigns** - "Generate product showcase videos at scale"
- **Personal branding** - "Create content without being on camera"

**Examples:**
- Input: `"A modern office with people collaborating, warm lighting"`
- Output: 8-second AI-generated video clip

- Input: Script file for "How to Make Cold Brew Coffee"
- Output: Complete video with scenes, transitions, and captions

---

## How This Skill Relates to Others

### Central Hub of Video Production

**Video Creator** sits in the middle of the workflow:

```
Storyboard Writer -> Video Creator -> Caption Creator -> Video Editor
```

1. **Storyboard Writer** - Plans what to create
2. **Video Creator** - Generates the content
3. **Caption Creator** - Adds accessibility
4. **Video Editor** - Polishes and exports

---

## Templates Included

| Template | Best For | Includes |
|----------|----------|----------|
| product_showcase | E-commerce | Product shots, features, CTA |
| social_post | Instagram/TikTok | Hook, body, engagement |
| tutorial | Education | Steps, instructions, summary |
| testimonial | Marketing | Quote, person, company |
| podcast_clip | Audio content | Waveform, captions, branding |

---

## Troubleshooting

**"API key error"**
- Set `KIE_API_KEY` environment variable

**"MoviePy error"**
- Run: `pip install moviepy opencv-python --upgrade`

**"No video output"**
- Check disk space and write permissions

**"AI generation failed"**
- Check API key validity and credit balance on KIE.AI