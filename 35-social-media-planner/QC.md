# Social Media Planner (Skill 35) - Quality Control Checklist

This is the standalone QC reference for Skill 35. The full QC system with failure handling and retry logic is documented in references/playbook.md Section 19.

QC runs BEFORE any content is scheduled. Nothing goes to GHL until all checks pass.

---

## Text Content (every post, every platform)

- [ ] Content aligns with client's brand tone and voice from core files
- [ ] Content uses brand-appropriate language (no profanity, no vulgar language)
- [ ] Content is appropriate for the client's target audience
- [ ] No sexually suggestive content of any kind
- [ ] Zone 1 (Mobile Hook) is within the platform's character limit
- [ ] Zone 2 (Desktop Hook) is within the platform's character limit (if applicable)
- [ ] Total post length is within the platform's maximum character limit
- [ ] No em dashes anywhere in the content
- [ ] No misspellings
- [ ] Emojis are present but never more than 3 per post
- [ ] The recap (starting Day 2) is woven into the middle of the value zone, NOT at the beginning
- [ ] The pitch matches the day's intensity level (soft Day 1, maximum Day 7)
- [ ] The cliffhanger is present at the end (Days 1-6 tease next day, Day 7 teases next week)
- [ ] The "check the comments" directive is present in the post body
- [ ] The pitch creates an emotionally compelling reason to schedule an appointment
- [ ] The series label is present (e.g., "Three of Seven")
- [ ] Hashtags follow platform-specific guidelines
- [ ] Content tone is emotionally visceral but not salesy

## Persona Governance (new check)

- [ ] Content persona was selected via 5-layer alignment OR client chose personal tone
- [ ] Persona selection is logged in persona-selection-log.md
- [ ] Content style is consistent with the selected persona's methodology throughout all 7 days
- [ ] If client overrode with personal tone, content matches soul.md voice and style
- [ ] Persona does not change mid-week (same persona governs all 7 days unless client requests otherwise)

## Comments (every post, every day)

- [ ] Comment is unique (not duplicated from any other day's comment)
- [ ] Comment ties directly to that day's specific topic (congruency)
- [ ] Comment ends with the current weekly action link (confirmed during heartbeat)
- [ ] Action link matches what the client provided for this week
- [ ] Comment tone is empathetic, understanding, urgent but not pushy
- [ ] No em dashes in the comment
- [ ] No misspellings in the comment

## Images (every image)

- [ ] Image prompt is appropriate for the client's brand and target audience
- [ ] Image contains NO sexually suggestive content
- [ ] Image contains NO violent or inappropriate imagery
- [ ] Image uses client's brand colors from core files
- [ ] Image is generated at the correct ratio for the platform (4:5, 2:3, or 9:16)
- [ ] Image is generated at the correct pixel dimensions
- [ ] Image includes text overlay (title/headline)
- [ ] Text on image does not cover faces
- [ ] Font on image is creative (not generic)
- [ ] Spelling on image text is correct
- [ ] Image file format is correct (PNG or JPG)

## Posting Verification (critical)

- [ ] Regular posts: image URL is in the `mediaUrls` field of the GHL API call (bundled with content)
- [ ] Carousel posts: ALL carousel image URLs are in the `mediaUrls` array (bundled with content)
- [ ] Video posts: video URL is in the `mediaUrls` field (bundled with content)
- [ ] Comments: posted as SEPARATE API call with parent post ID, 1-2 minutes after parent
- [ ] No post is sent without its corresponding image/video attached
- [ ] No comment is missing its action link

## Scheduling

- [ ] Post is scheduled for the correct day (Sunday = Day 1, Monday = Day 2, etc.)
- [ ] Post is scheduled for 9:00 AM
- [ ] Comment is scheduled 1-2 minutes after the post
- [ ] All 6 platforms have posts scheduled for each day
- [ ] Carousel is scheduled for Thursday
- [ ] Email newsletter is scheduled for Tuesday at 9:00 AM
- [ ] Blog, podcast, and grand finale are scheduled for Day 7

## Google Sheet Verification

- [ ] Webhook POST to `https://main.blackceoautomations.com/webhook/social-planner-sheet-create` successful
- [ ] Request payload includes `brandName` and `clientEmail`
- [ ] Response received with `sheetUrl`, `sheetId`, and `sheetName`
- [ ] Sheet URL stored in MEMORY.md
- [ ] Client has edit access to the created sheet
- [ ] Fallback documented if webhook fails (template link provided to client)

## Blog Post

- [ ] Word count is between 1,500-2,500 words
- [ ] Soft pitch is in the middle (around 50% mark)
- [ ] Intentional pitch is at the end
- [ ] SEO elements are present (title, meta description, subheadings, keywords)
- [ ] Featured image is generated at 16:9 (1200x630)
- [ ] No em dashes
- [ ] No misspellings

## Podcast Script

- [ ] Script length is 1,500-2,000 words
- [ ] Fish Audio S2 emotion tags are present in [square brackets]
- [ ] Script covers all 7 days of content
- [ ] Pitch is woven naturally toward the end
- [ ] CTA is present
- [ ] Next week tease is present
- [ ] No em dashes
- [ ] No misspellings

## Podcast Audio

- [ ] Audio is MP3 format
- [ ] Bitrate is 192 kbps
- [ ] Duration is 10-15 minutes

## Podcast Cover Image (Podbean/Apple Requirements)

- [ ] Format is JPEG (.jpg) or PNG (.png) ONLY. NO WebP, GIF, or other formats (Apple Podcasts rejects them)
- [ ] Aspect ratio is 1:1 square
- [ ] Dimensions are at least 1400 x 1400 px (and no more than 3000 x 3000 px)
- [ ] File size is under 500 KB. If larger, resize before sending (reduce resolution or increase JPEG compression)
- [ ] Color space is RGB
- [ ] Image uses client brand colors and visually represents the weekly theme

## Podcast Publishing (Webhook Payload)

- [ ] Audio file uploaded to GHL Media Library first (NOT a Fish Audio URL)
- [ ] Cover image uploaded to GHL Media Library first
- [ ] podcast_id matches the client's Podbean channel ID
- [ ] publish_date is in ISO 8601 format WITH time component (e.g., 2026-04-12T09:00:00)
- [ ] publish_date is set for Day 7 (Saturday) at 9:00 AM Eastern
- [ ] description is under 3000 characters
- [ ] episode_type is "full" (unless trailer or bonus)
- [ ] explicit is "clean" (unless content is explicit)
- [ ] client_email, client_first_name, client_last_name are correct
- [ ] No episode number is included in the payload (automation assigns it)

## Video Content QC Checklist

- [ ] Duration exactly 60 seconds (`ffprobe -v quiet -show_entries format=duration -of csv=p=0 final.mp4`)
- [ ] Resolution 1080x1920 (9:16) (`ffprobe -v quiet -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x final.mp4`)
- [ ] Video codec H.264 (`ffprobe -v quiet -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 final.mp4`)
- [ ] Audio codec AAC 192kbps (`ffprobe -v quiet -select_streams a:0 -show_entries stream=bit_rate,codec_name -of csv=p=0:s=,x final.mp4`)
- [ ] Frame rate 30fps (`ffprobe -v quiet -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 final.mp4`)
- [ ] Smooth crossfade transitions between segments (visual inspection)
- [ ] 3-second brand intro (first frames match [from identity.md: brand colors/logo])
- [ ] 3-second brand outro with CTA
- [ ] ffprobe no errors (`ffprobe final.mp4` returns clean streams)
- [ ] Audio perfectly synced to video
- [ ] Bitrate: video ~5Mbps, total <100MB for GHL upload
- [ ] MP4 container, faststart enabled (`qt-faststart` or `-movflags +faststart`)
- [ ] No black/blank frames
- [ ] Consistent lighting/color grading
- [ ] Text overlays readable (min 24pt, high contrast)
- [ ] Brand colors used throughout
- [ ] Content appropriate (no violations, matches weekly theme)

---

## Email Newsletter QC Checklist

- [ ] Subject line ≤60 characters
- [ ] Preview text ≤120 characters
- [ ] Table-based layout (max-width: 600px)
- [ ] Inline CSS only (no <style> or external)
- [ ] Mobile responsive (tested 320px-600px)
- [ ] Images from GHL Media Library (<img src="[media_url]");
- [ ] Alt text on all images
- [ ] 3-column table: image | recap | CTA
- [ ] Brand colors from identity.md
- [ ] No em dashes
- [ ] No broken links
- [ ] Pitch in middle (Day 2 intensity)
- [ ] CTA button prominent (min 44px height)
- [ ] Deferred send scheduled Tuesday 9AM

## QC Failure Process

1. QC agent flags the specific failing check
2. Content is automatically revised to fix the flagged issue
3. QC agent re-checks the revised content
4. If it fails again, retry the revision up to 3 total attempts
5. After 3 failures: notify the client via Telegram with the specific failure details and which check failed

## QC Agent Assignments

| Agent | Responsibility |
|-------|----------------|
| QC Agent 1 | Text content + persona governance (all 7 days, all 8 platforms) |
| QC Agent 2 | Comments (all 42+ comments) |
| QC Agent 3 | Images (all 21+ images) |
| QC Agent 4 | Blog + Email |
| QC Agent 5 | Podcast + Video |
| QC Agent 6 | Schedule + Bundle verification |
