# Video Creator Skill - Examples

Real-world usage examples and use cases.

## Table of Contents

1. [Quick Examples](#quick-examples)
2. [Marketing Videos](#marketing-videos)
3. [Social Media Content](#social-media-content)
4. [Educational Content](#educational-content)
5. [Product Demonstrations](#product-demonstrations)
6. [Podcast Clips](#podcast-clips)
7. [AI Avatar Videos](#ai-avatar-videos)
8. [Batch Processing](#batch-processing)

---

## Quick Examples

### Example 1: Simple Text-to-Video

Create a 5-second video from a text description:

```bash
python scripts/text_to_video.py "A peaceful Japanese garden with cherry blossoms" \
  --duration 5 \
  --output garden.mp4
```

### Example 2: Multi-Clip Montage

Combine vacation clips with music:

```bash
python scripts/multi_clip_assembly.py \
  vacation/day1.mp4 \
  vacation/day2.mp4 \
  vacation/day3.mp4 \
  --transition fade \
  --music audio/upbeat.mp3 \
  --output vacation_montage.mp4
```

### Example 3: Product Highlight

Using the product showcase template:

```bash
# Create product data file
# Prerequisites: the listed images and audio/upbeat.mp3 must already exist.
cat > product_data.json << 'EOF'
{
  "product_name": "EcoBottle Pro",
  "tagline": "Stay Hydrated, Save the Planet",
  "images": ["photos/bottle1.jpg", "photos/bottle2.jpg", "photos/bottle3.jpg"],
  "features": [
    "24hr Cold / 12hr Hot",
    "BPA-Free Stainless Steel",
    "Lifetime Warranty"
  ],
  "price": "$29.99",
  "call_to_action": "Order Now at ecobottle.com",
  "music": "audio/upbeat.mp3",
  "duration": 30
}
EOF

# Generate video
python scripts/template_video.py product_showcase --data product_data.json
```

---

## Marketing Videos

### Product Launch Video

Create a professional product launch video:

```bash
# Step 1: Generate intro clip
python scripts/text_to_video.py \
  "Cinematic shot of sleek smartphone rotating on black background, studio lighting" \
  --duration 3 --style cinematic --output intro.mp4

# Step 2: Generate feature clips
python scripts/text_to_video.py "Close-up of smartphone camera lens capturing vibrant colors" \
  --duration 2 --output feature1.mp4

python scripts/text_to_video.py "Hand holding smartphone displaying beautiful interface" \
  --duration 2 --output feature2.mp4

# Step 3: Generate outro
python scripts/text_to_video.py "Product logo reveal with dramatic lighting" \
  --duration 2 --output outro.mp4

# Step 4: Assemble with transitions and music
python scripts/multi_clip_assembly.py \
  intro.mp4 feature1.mp4 feature2.mp4 outro.mp4 \
  --transition fade \
  --music audio/epic.mp3 \
  --output product_launch.mp4
```

### Promotional Social Video

```bash
# Prerequisite: audio/upbeat.mp3 must already exist.
cat > promotional_social.json << 'EOF'
{
  "platform": "instagram",
  "headline": "Summer Sale!",
  "subheadline": "Up to 50% Off Everything",
  "duration": 15,
  "music": "audio/upbeat.mp3"
}
EOF
python scripts/template_video.py social_post --data promotional_social.json
```

---

## Social Media Content

### Instagram Reels / TikTok

Create vertical short-form content:

```bash
# Image to video with motion
python scripts/image_to_video.py photo.jpg \
  --motion ken_burns \
  --duration 5 \
  --resolution 1080p \
  --output reel.mp4

# Add trending audio
python scripts/add_music.py reel.mp4 \
  --music audio/trending.mp3 \
  --output reel_final.mp4
```

### YouTube Shorts

```bash
# Create from script
python scripts/script_to_video.py shorts_script.txt \
  --quality social \
  --output shorts.mp4
```

Script format (`shorts_script.txt`):
```
SCENE 1: [Bold text "3 Tips for Better Sleep" on gradient background]
TEXT: 3 Tips for Better Sleep
DURATION: 2s

SCENE 2: [Dark bedroom with soft lighting]
TEXT: 1. Keep it cool (65°F)
DURATION: 3s

SCENE 3: [Person putting phone away]
TEXT: 2. No screens 1hr before bed
DURATION: 3s

SCENE 4: [Peaceful meditation scene]
TEXT: 3. Try meditation
DURATION: 3s

SCENE 5: [Subscribe animation]
TEXT: Subscribe for more tips!
DURATION: 2s
```

### LinkedIn Professional Content

```bash
# Prerequisite: audio/corporate.mp3 must already exist.
cat > linkedin_post.json << 'EOF'
{
  "platform": "linkedin",
  "headline": "5 Leadership Lessons",
  "subheadline": "Lead by example, communicate clearly, and empower your team.",
  "duration": 45,
  "music": "audio/corporate.mp3"
}
EOF
python scripts/template_video.py social_post --data linkedin_post.json
```

---

## Educational Content

### Tutorial Video

```bash
# Prerequisite: audio/calm.mp3 must already exist.
cat > tutorial_data.json << 'EOF'
{
  "title": "Python Basics: Variables",
  "instructor": "Jane Smith",
  "sections": [
    {
      "heading": "What are Variables?",
      "content": "Variables are containers for storing data values.",
      "duration": 30
    },
    {
      "heading": "Creating Variables",
      "content": "Assign a value with syntax such as x = 5 or name = 'Ada'.",
      "duration": 45
    },
    {
      "heading": "Variable Types",
      "content": "Python has int, float, string, and bool types",
      "duration": 60
    }
  ],
  "music": "audio/calm.mp3"
}
EOF
python scripts/template_video.py tutorial --data tutorial_data.json
```

### Online Course Promo

```bash
# Generate course preview clips
for i in {1..5}; do
  python scripts/text_to_video.py "Scene $i from course: animated educational content" \
    --duration 3 --output course_clip_$i.mp4
done

# Assemble, then attach the required audio tracks
python scripts/multi_clip_assembly.py course_clip_*.mp4 \
  --transition fade \
  --output course_preview_silent.mp4

python scripts/add_music.py course_preview_silent.mp4 \
  --voiceover narration/course_intro.mp3 \
  --music audio/calm.mp3 \
  --output course_preview.mp4
```

---

## Product Demonstrations

### App Demo Video

```bash
# Create screen recording montage
python scripts/multi_clip_assembly.py \
  demos/onboarding.mp4 \
  demos/dashboard.mp4 \
  demos/features.mp4 \
  --transition fade \
  --music audio/corporate.mp3 \
  --output app_demo.mp4
```

### Physical Product Demo

```bash
# Generate product showcase from images
# Prerequisite: every product image listed below must already exist.
cat > product_showcase.json << 'EOF'
{
  "product_name": "Smart Home Hub",
  "images": [
    "product/angle1.jpg",
    "product/angle2.jpg",
    "product/in_use.jpg",
    "product/app_interface.jpg"
  ],
  "features": [
    "Voice Control",
    "Automated Routines",
    "Energy Monitoring",
    "Works with 500+ Devices"
  ],
  "duration": 60
}
EOF
python scripts/template_video.py product_showcase --data product_showcase.json
```

---

## Podcast Clips

### Audiogram for Social Media

```bash
# Prerequisite: podcast/episode45_clip.mp3 must already exist.
cat > podcast_clip.json << 'EOF'
{
  "audio_file": "podcast/episode45_clip.mp3",
  "quote_text": "The key to success is consistency, not intensity.",
  "speaker": "Guest Name",
  "podcast_name": "The Business Show",
  "duration": 30
}
EOF
python scripts/template_video.py podcast_clip --data podcast_clip.json
```

### Full Episode from a Script

```bash
python scripts/script_to_video.py podcast_script.txt --quality web --output podcast_video.mp4
```

Script format:
```
SCENE 1: [Show logo animation]
DURATION: 15s

SCENE 2: [Display chapter title card]
TEXT: Marketing Strategies 2024
DURATION: 600s

SCENE 3: [Bullet points appearing]
DURATION: 60s
```

---

## AI Avatar Videos

### Presenter-Style Video

```bash
python scripts/avatar_video.py \
  --script presentation.txt \
  --avatar professional_female_1 \
  --background office_blur \
  --output training_video.mp4
```

Presentation script (`presentation.txt`):
```
Hello team, welcome to this quarter's sales training.

[SLIDE: Sales Targets Chart]
This quarter we're focusing on three key areas.

[SLIDE: Customer Retention]
First, customer retention. It's 5x cheaper to keep existing customers.

[SLIDE: Upselling]
Second, strategic upselling to increase average order value.

Thank you for your attention!
```

### Personalized Sales Videos

```bash
# Render pre-personalized scripts (one script per recipient)
for script in personalized_scripts/*.txt; do
  python scripts/avatar_video.py \
    --script "$script" \
    --output "personalized/$(basename "$script" .txt).mp4"
done
```

---

## Batch Processing

### Process Multiple Scripts

```bash
#!/bin/bash
# batch_create.sh

INPUT_DIR="scripts/"
OUTPUT_DIR="output/"

for script in "$INPUT_DIR"/*.txt; do
  filename=$(basename "$script" .txt)
  echo "Processing: $filename"
  
  python scripts/script_to_video.py "$script" \
    --output "$OUTPUT_DIR/$filename.mp4" \
    --quality web
done

echo "Batch processing complete!"
```

### Extract Thumbnail Frames from Videos

```bash
# Use ffmpeg directly to grab a frame as a thumbnail
for video in output/*.mp4; do
  ffmpeg -i "$video" -ss 00:00:03 -vframes 1 \
    "thumbnails/$(basename $video .mp4).jpg"
done
```

### Repurpose Content for Multiple Platforms

```bash
VIDEO="master_content.mp4"

# YouTube version (16:9, high quality)
ffmpeg -i "$VIDEO" -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" youtube_version.mp4

# Instagram (1:1 square, center crop)
ffmpeg -i "$VIDEO" -vf "crop=min(iw\,ih):min(iw\,ih),scale=1080:1080" instagram_version.mp4

# TikTok/Reels (9:16 vertical)
ffmpeg -i "$VIDEO" -vf "crop=iw*9/16:ih,scale=1080:1920" tiktok_version.mp4

# Twitter/X (2:1)
ffmpeg -i "$VIDEO" -vf "crop=iw:iw/2,scale=1280:640" twitter_version.mp4
```

---

## Advanced Workflows

### A/B Testing Different Intros

```bash
# Create versions using supported style presets
for style in cinematic animated realistic; do
  python scripts/text_to_video.py "Product intro variation in $style style" \
    --style "$style" \
    --output "ab_test/intro_$style.mp4"
  
  # Combine with common content
  python scripts/multi_clip_assembly.py \
    "ab_test/intro_$style.mp4" \
    content/main_message.mp4 \
    --output "ab_test/final_$style.mp4"
done
```

### Automated Weekly Content

```bash
#!/bin/bash
# weekly_content.sh - Run every Monday

WEEK=$(date +%U)
YEAR=$(date +%Y)

# Generate weekly roundup
## Tips & Best Practices

1. **Start Small**: Test with 5-10 second clips before creating full videos
2. **Use Templates**: Templates ensure consistency across your brand
3. **Preview Transitions**: Use `python scripts/transitions.py --preview fade` before final assembly
4. **Organize Assets**: Keep images, audio, and scripts in structured folders
5. **Batch Similar Tasks**: Group operations to save time
6. **Quality vs Speed**: Use `--quality web` for drafts, `--quality cinema` for final
7. **Audio Matters**: Good audio improves engagement more than perfect visuals
8. **Keep It Short**: Social videos perform best under 60 seconds

---

## Troubleshooting Examples

### Fix Audio Sync

```bash
# Use ffmpeg to shift audio by -0.5 seconds
ffmpeg -i video.mp4 -itsoffset -0.5 -i video.mp4 -map 0:v -map 1:a -c copy fixed.mp4
```

### Extract and Recombine

```bash
# Extract audio using add_music.py extract subcommand
python3 scripts/add_music.py video.mp4 extract --output audio.wav

# Edit audio externally, then recombine
ffmpeg -i video.mp4 -i edited_audio.wav -map 0:v -map 1:a -c:v copy -shortest final.mp4
```

### Convert Format

```bash
# Use ffmpeg directly for format conversion
ffmpeg -i video.mov -c:v libx264 -c:a aac video.mp4
```
