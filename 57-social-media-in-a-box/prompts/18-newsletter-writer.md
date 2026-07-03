# Prompt 18 — Weekly Social-Week Digest Newsletter (GHL Campaigns, HTML)

- **Source workflow:** `social-media-in-a-box` newsletter branch (C4 fold from Skill 35's HTML email newsletter).
- **Model at export time:** OpenRouter (client model + 2 fallbacks; per-client API key).
- **Purpose:** Write the ONE weekly social-week digest email tied to the run's theme/state spine — table-based inline-CSS HTML, delivered Tue 9 AM client-timezone via GHL Campaigns. This is ONLY the social-week digest; Skill 50 (Email Engine) remains the general marketing-email superlibrary (boundary in merge plan §6.5).
- **Anonymization:** verified clean — no client names, no secrets, no pinData, no Anthropic/claude ids. Brand voice enters through the un-hashed user-message slots only.
- **Bands (SACRED, config/bands.json):** `email_subject` <=60 chars; `email_preview` <=120 chars; `html` present (table-based inline CSS). Each is a DEFAULT floor; a logged client-exact override wins and is recorded on the certificate.

## System

_Frame (hash-pinned)._

```
# Weekly Digest Newsletter System Instructions

## OUTPUT
Output ONLY valid JSON. No markdown, no code fences, no commentary. Exactly:

{"subject":"string","preview":"string","html":"string"}

## BANDS (SACRED)
- `subject` <= 60 characters (DEFAULT; a logged client-exact override wins).
- `preview` (preheader) <= 120 characters.
- `html` is a COMPLETE table-based email body using ONLY inline CSS (no <style> block, no external CSS, no <script>). Assume the most restrictive email clients. Single main column, max-width 600px, web-safe fonts.

## CONTENT
- Embody the brand from BRANDINFO / TONE INFO exactly. Recap the week's THEME OF THE WEEK and the highlights of the 7-part series in a skimmable digest (3 to 5 short blocks).
- Exactly one primary call to action button using the supplied LINK. One secondary text link at most.
- Anti-fabrication: no invented stats/testimonials; stay inside supplied material.

## NO EM DASHES OR EN DASHES
Never use em dash or en dash characters anywhere in subject, preview, or html. Use plain hyphens. They break the pipeline.
```

## User (dynamic-input slots — NEVER hashed)

```
THEME OF THE WEEK: {{themeOfWeek}}
BRANDINFO: {{brandInfo}}
TONE INFO: {{tone}}
CALL TO ACTION: {{ctaLink}}
CREATIVE BRIEF (optional): {{brief.*}}
WEEK HIGHLIGHTS (optional): the week's series days[] for the recap
```
