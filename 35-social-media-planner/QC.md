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

---

## 🔴 INSTALL-TIME QC RUBRIC (v2.0.0+)

The checks above are CONTENT QC — they run weekly during content production. This section is **INSTALL QC** — it runs once during skill activation. The install is NOT complete until this scores 8.5/10 or higher.

### Score breakdown (10 points total)

| Section | Points | What it tests |
|---|---|---|
| Prerequisites | 1.5 | Skills 01, 02, 22, 31 installed. Skill 36 detection handled. Skill 30 present OR podcast deferred. |
| Credentials (canonical names) | 2.0 | `GOHIGHLEVEL_API_KEY` (PIT) AND `GOHIGHLEVEL_LOCATION_ID` present at canonical secrets path (`~/.openclaw/secrets/.env` on Mac / `~/.openclaw/secrets/.env` on VPS). Deprecated names (`GHL_PRIVATE_TOKEN`, `GHL_API_KEY`, `GHL_LOCATION_ID`) NOT used. |
| GHL access verified | 1.5 | Smoke test against `get_platform_accounts` (MCP) or `/social-media-posting/oauth/.../facebook/accounts` (direct API) returned 200 with real data. No 403s (= scopes correct). |
| MCP routing detected | 1.0 | If Skill 36 installed: routing mode = mcp-first AND `$GHL_COMMUNITY_MCP_URL` resolves. If Skill 36 NOT installed: routing mode = direct-api AND warning logged in MEMORY.md. |
| Software present | 1.0 | FFmpeg ≥4.0, ImageMagick, python3 all working. |
| First-Run Protocol complete | 1.0 | Brand info extracted from core files. Google Sheet created via webhook. Action link stored. Video preference stored. Notification channel stored. Podcast question answered. |
| Core .md updates applied surgically | 1.0 | AGENTS.md + TOOLS.md + MEMORY.md got the labeled CORE_UPDATES sections. SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md NOT touched by this skill. |
| Weekly theme cron registered (AUTO-FAIL) | 0.5 | `register-weekly-cron.sh` exited 0. Programmatic check: `openclaw cron list \| grep -c skill35-weekly-theme` == 1 (exactly one entry). Entry shows `main` sessionTarget and schedule `0 8 * * 6`. HEARTBEAT.md does NOT contain the ungated Saturday 8:00 AM block. If this check fails, QC HARD-FAILS regardless of total score — the weekly trigger is non-negotiable. |
| Client confirmation sent | 0.5 | The owner-facing summary message was sent (Telegram or whichever channel they use). |

### Pass / Fail / Loop

- **9.5–10.0:** Excellent. Skill is fully active. No follow-up needed.
- **8.5–9.4:** Pass. The install is complete. Surface the minor items as "pending" in the client summary message.
- **7.0–8.4:** **DO NOT declare done.** Loop back, fix the items that lost points, re-score. Max 5 loops.
- **Below 7.0:** Stop. Escalate to the operator on Telegram (`env.vars.OPERATOR_TELEGRAM_CHAT_ID`, default `5252140759`) with: which section scored what, what failed, what fix you tried, what's blocking. Resolve via the helper:
  ```bash
  source ~/.openclaw/skills/shared-utils/operator-chat-id.sh
  openclaw message send --channel telegram --target "$OPERATOR_CHAT_ID" --message "..."
  ```

### Required actions when below 8.5

1. Re-check the checklist above by section. Identify which sections fell short.
2. Apply the smallest possible fix per section.
3. Re-run the relevant checks (don't re-do the whole skill — just the failed sections).
4. Re-score. If still below 8.5, count this as a loop iteration.
5. After 5 loops, stop and escalate. Don't keep looping silently.

### Cron presence assertion (AUTO-FAIL gate)

Run this check as part of QC. If it fails, QC hard-fails regardless of total score — the weekly trigger is non-negotiable.

```bash
# AUTO-FAIL: Skill 35 must have exactly 1 skill35-weekly-theme cron, main target, 0 8 * * 6.
_count="$(openclaw cron list 2>/dev/null | grep -c "skill35-weekly-theme" || true)"
if [ "$_count" -ne 1 ]; then
  echo "QC AUTO-FAIL: expected exactly 1 skill35-weekly-theme cron, found $_count." >&2
  echo "Run: bash ~/.openclaw/skills/35-social-media-planner/scripts/register-weekly-cron.sh" >&2
  exit 1
fi
_main_count="$(openclaw cron list 2>/dev/null | grep "skill35-weekly-theme" | grep -c "main" || true)"
if [ "$_main_count" -lt 1 ]; then
  echo "QC AUTO-FAIL: skill35-weekly-theme cron does not have sessionTarget=main." >&2
  exit 1
fi
echo "QC PASS: skill35-weekly-theme cron present (1 entry, main target)."
```

### Bundled validation script

If `qc-skill35.sh` exists in this folder, run it. It must exit 0 in addition to the rubric scoring 8.5+. The script catches mechanical things the rubric assumes (e.g., env-var format validation, file mode 600 on secrets, webhook reachability).

---

## What v2.0.0 changed in QC.md (May 13, 2026)

- Added the install-time rubric above with 0–10 scoring and the 8.5 gate.
- Renamed the old failure process to "content QC failure" to distinguish from install QC.
- Loop-until-passing rule added (max 5 loops, then escalate).
- Bundled `qc-skill35.sh` script referenced (added separately).

---

## SKILL DOCUMENTATION INTEGRITY (auto-fail gate — run before any install or release)

These checks guard against stale platform lists that cause agents to give incomplete answers to owner scope questions. A single failure in this section is an automatic hard fail — do not proceed with install or release until resolved.

- [ ] **SKILL.md description** does NOT contain the stale string "8 platforms (WordPress, Medium, Substack, LinkedIn, GHL blog, YouTube, X/Twitter, Facebook)". It MUST describe the enabled-channels model.
- [ ] **SKILL.md Purpose** names Facebook, Instagram, LinkedIn, X/Twitter, TikTok, Pinterest, and Google Business Profile as primary GHL Social Planner channels.
- [ ] **SKILL.md Purpose** names WordPress, Medium, Substack, and YouTube as OPTIONAL add-ons (not primary).
- [ ] **SKILL.md** contains the "Owner Q&A Playbook" section with the mandatory live-check-before-answering rule.
- [ ] **INSTRUCTIONS.md "What this skill does"** does NOT contain the stale string "8 platforms: WordPress, Medium, Substack, LinkedIn articles, GHL blog, YouTube, X/Twitter, Facebook". It MUST reference the enabled-channels model.
- [ ] **INSTRUCTIONS.md** contains the "Owner scope question — LIVE CHECK MANDATORY" section.
- [ ] **INSTRUCTIONS.md** banned-failure rule covers BOTH connection-status answers AND scope/capability answers.
- [ ] **SKILL.md**, **INSTRUCTIONS.md**, **README.md**, and **CORE_UPDATES.md** all describe the same primary channel set (Facebook, Instagram, LinkedIn, X/Twitter, TikTok, Pinterest) — no file carries a contradictory older list.
- [ ] Instagram is named as a primary platform in SKILL.md, INSTRUCTIONS.md, README.md, and CORE_UPDATES.md.
- [ ] TikTok is named as a primary platform in SKILL.md, INSTRUCTIONS.md, README.md, and CORE_UPDATES.md.
- [ ] Carousels (Thursday carousel strategy) are mentioned in SKILL.md as a content type.

**How to check programmatically:**
```bash
# Must return zero matches (stale string absent):
grep -r "8 platforms.*WordPress.*Medium.*Substack.*LinkedIn.*GHL blog.*YouTube.*X/Twitter.*Facebook" \
  ~/.openclaw/skills/35-social-media-planner/ && echo "FAIL: stale platform list found" || echo "PASS: stale string absent"

# Must return matches (correct strings present in SKILL.md):
grep -l "Instagram" ~/.openclaw/skills/35-social-media-planner/SKILL.md \
  && grep -l "TikTok" ~/.openclaw/skills/35-social-media-planner/SKILL.md \
  && grep -l "Owner Q&A Playbook" ~/.openclaw/skills/35-social-media-planner/SKILL.md \
  && echo "PASS: required strings present" || echo "FAIL: required strings missing"
```

## QC Agent Assignments

| Agent | Responsibility |
|-------|----------------|
| QC Agent 1 | Text content + persona governance (all 7 days, all 8 platforms) |
| QC Agent 2 | Comments (all 42+ comments) |
| QC Agent 3 | Images (all 21+ images) |
| QC Agent 4 | Blog + Email |
| QC Agent 5 | Podcast + Video |
| QC Agent 6 | Schedule + Bundle verification |
