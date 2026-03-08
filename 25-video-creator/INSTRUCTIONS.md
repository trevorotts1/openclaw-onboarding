# Video Creator Skill - Complete Instructions

## What This Skill Is

The **Video Creator Skill** generates videos from scratch using AI. Text-to-video, script-to-video, image animation, and multi-clip assembly with transitions and music.

**Purpose:** Create professional videos without filming anything. Turn ideas, scripts, or images into polished video content.

---

## What It Does

1. **Text-to-Video** - AI generates video from text descriptions
2. **Script-to-Video** - Converts written scripts into video scenes
3. **Image-to-Video** - Animates still images (Ken Burns effect, etc.)
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
openclaw skill install video-creator.skill
```

Or manually:
```bash
unzip video-creator.skill -d ~/.openclaw/skills/
chmod +x ~/.openclaw/skills/video-creator/scripts/*.py
```

### Step 3: Configure AI Providers
```bash
# Set your API keys in environment
export KIE_API_KEY="your_key_here"
export RUNWAY_API_KEY="your_key_here"  # Optional
```

---

## How to Run

### Text to Video
```bash
python3 ~/.openclaw/skills/video-creator/scripts/text_to_video.py \
  --prompt "A serene mountain landscape at sunset, cinematic" \
  --duration 8 \
  --output mountain.mp4
```

### Script to Video
```bash
python3 ~/.openclaw/skills/video-creator/scripts/script_to_video.py \
  --script script.txt \
  --template tutorial \
  --output video.mp4
```

### Image to Video
```bash
python3 ~/.openclaw/skills/video-creator/scripts/image_to_video.py \
  --image photo.jpg \
  --effect zoom_pan \
  --duration 5 \
  --output animated.mp4
```

### Add Music
```bash
python3 ~/.openclaw/skills/video-creator/scripts/add_music.py \
  --video video.mp4 \
  --music background.mp3 \
  --output final.mp4
```

---

## Memory File Updates Required

### Update TOOLS.md
```markdown
### Video Creator
- **Purpose:** Generate videos from text/scripts/images
- **Location:** ~/.openclaw/skills/video-creator/
- **Key Scripts:** text_to_video.py, script_to_video.py, image_to_video.py
- **Dependencies:** moviepy, opencv-python, requests, pillow
- **AI Providers:** KIE.AI (Veo, Sora, Kling, etc.)
- **Templates:** product_showcase, social_post, tutorial, testimonial, podcast_clip
```

### Update AGENTS.md
```markdown
## Video Creator Agent
I can create videos from scratch:
- Text-to-video generation
- Script-to-video conversion
- Image animation and effects
- Multi-clip assembly with transitions
- AI avatar/presenter videos
- Background music mixing

Templates available for: tutorials, social posts, testimonials, products
```

### Update USER.md
```markdown
## Video Creation Preferences
- Default AI model: [veo-3-1/sora-25s/etc]
- Preferred video style: [cinematic/minimal/energetic]
- Typical video length: [seconds/minutes]
- Music preference: [genre/style]
```

### Update IDENTITY.md (Optional)
```markdown
### Video Production Specialist
I create professional videos using AI generation, helping clients produce content without traditional filming equipment.
```

---

## GitHub Repositories Used

1. **Zulko/moviepy** - Video editing and composition
   - https://github.com/Zulko/moviepy
   - Core video manipulation

2. **opencv/opencv-python** - Computer vision
   - https://github.com/opencv/opencv-python
   - Image processing and effects

3. **KIE.AI API** - AI video generation
   - Veo 3.1, Sora 2, Kling 3.0, Seed Dance, Wan 2.6
   - Requires API key from KIE.AI

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
- Input: "A modern office with people collaborating, warm lighting"
- Output: 8-second AI-generated video clip

- Input: Script for "How to Make Cold Brew Coffee"
- Output: Complete video with scenes, transitions, and captions

**Benefits:**
- No filming equipment needed
- No actors or locations
- Generate unlimited variations
- Consistent quality and style
- Fraction of traditional video cost

---

## How This Skill Relates to Others

### Central Hub of Video Production

**Video Creator** sits in the middle of the workflow:

```
Storyboard Writer → Video Creator → Caption Creator → Video Editor
```

1. **Storyboard Writer** - Plans what to create
2. **Video Creator** - Generates the content
3. **Caption Creator** - Adds accessibility
4. **Video Editor** - Polishes and exports

### Also Works With Video Editor
- Generate raw clips (Video Creator)
- Cut, resize, add B-roll (Video Editor)
- Final export

---

## Combined Usage Examples

### Example 1: Complete Social Media Video
```bash
# 1. PLAN
storyboard-writer --duration 60 --model sora-10s --topic "Morning Routine"

# 2. CREATE
video-creator --script morning_routine.txt --template social_post --output raw.mp4

# 3. CAPTION
caption-creator --input raw.mp4 --output with_captions.mp4 --style animated

# 4. EDIT (resize for platform)
video-editor --input with_captions.mp4 --platform tiktok --output final.mp4
```

### Example 2: Product Video from Images
```bash
# Animate product photos
video-creator --image product1.jpg --effect zoom --output clip1.mp4
video-creator --image product2.jpg --effect pan --output clip2.mp4

# Combine with music
video-creator --assemble clip1.mp4 clip2.mp4 --music upbeat.mp3 --output product_demo.mp4

# Add captions
caption-creator --input product_demo.mp4 --output final.mp4
```

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
→ Set KIE_API_KEY environment variable

**"MoviePy error"**
→ Run: `pip install moviepy opencv-python --upgrade`

**"No video output"**
→ Check disk space and write permissions

**"AI generation failed"**
→ Check API key validity and credit balance on KIE.AI