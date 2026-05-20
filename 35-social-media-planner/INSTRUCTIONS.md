# Social Media Planner / Content Publishing Engine — Execution Instructions

**Version:** v10.12.0 (closes Audit Phase 11 — INSTRUCTIONS.md was missing)
**Skill:** 35-social-media-planner (a.k.a. Content Publishing Engine)
**Status:** Required runtime guide. Referenced from `SKILL.md` as part of the TYP read-order.

This is the **execution guide** for the 15+6 agent content publishing pipeline. `INSTALL.md` covers one-time setup; `SKILL.md` describes purpose. **This file covers how an agent actually runs a publishing cycle.**

---

## What this skill does

Orchestrate 15 production agents + 6 QC agents to research, create, produce, schedule, and publish content across **8 platforms**: WordPress, Medium, Substack, LinkedIn articles, GHL blog, YouTube, X/Twitter, Facebook. Also handles HTML email newsletters and podcast distribution.

The skill is **variable-driven** — every credential, URL, brand voice, and image-model setting is pulled from existing files. **Never hardcode a brand name, a domain, or a credential.**

---

## TYP read-order (mandatory)

1. `SKILL.md` — what the skill is and the 15+6 agent roster
2. **`INSTRUCTIONS.md` (this file)** — how to execute a cycle
3. `INSTALL.md` — re-read only if a step refers back to install state
4. `QC.md` — runtime QC rubric (separate from install QC)
5. `CORE_UPDATES.md` — what gets written to core .md files after install
6. `references/` — platform-specific cheat sheets (read only the platform you're publishing to)

Skipping is an N4 violation.

---

## Variable sources (NEVER hardcode)

The skill resolves variables at runtime from these sources. Confirm each is present before launching a cycle:

| Variable type | Source |
|---------------|--------|
| Brand voice, tone, mission | `~/.openclaw/SOUL.md`, `IDENTITY.md` |
| Owner profile, audience | `~/.openclaw/USER.md` |
| API keys (GHL, WordPress, Medium, etc.) | `~/.openclaw/credentials/.env` |
| Platform URLs, location IDs | `~/.openclaw/credentials/.env` (e.g., `GHL_LOCATION_ID`) |
| Image model preference | `~/.openclaw/config/image-model.json` |
| Video specs (resolution, bitrate) | `~/.openclaw/config/video-specs.json` |
| Posting cadence, time-of-day | `~/.openclaw/config/social-cadence.json` |

If any source is missing, **STOP** and surface the gap via the triple-fire trigger (N22). Do not invent a default.

---

## The 5-phase publishing cycle

### Phase 1 — Research & Strategy
**Agents:** Researcher, Strategist
**Inputs:** Topic (from user) OR upcoming-event signal (from calendar watcher)
**Outputs:** `strategy.md` with hooks, SEO targets, brand-voice-aligned angles

```
1. Researcher: memory_search + web_search on topic → raw data dump
2. Strategist: synthesizes into strategy.md, pulling voice from SOUL.md
```

### Phase 2 — Content Creation
**Agents:** Writer, Editor, Image Prompt Engineer, Image Generator, Video Script Writer, Audio Generator, Thumbnail Designer
**Outputs:** `article-draft.md`, `image-prompts.json`, generated images, `video-script.md`, audio files, thumbnails

```
1. Writer drafts → Editor refines
2. Image Prompt Engineer writes prompts → Image Generator produces images
3. (If video) Video Script Writer drafts → Audio Generator voices it → Thumbnail Designer makes the preview
```

### Phase 3 — Production
**Agents:** Video Producer (FFmpeg), Email Designer
**Outputs:** Final video files (with crossfades, intro/outro), HTML email body

FFmpeg pipeline reads specs from `~/.openclaw/config/video-specs.json` — do not pass resolution/bitrate as CLI args.

### Phase 4 — Schedule
**Agent:** Publisher (planning sub-step)
**Inputs:** Strategy + finished content + `social-cadence.json`
**Output:** `publish-schedule.json` (per-platform timestamps)

The Publisher does NOT post yet — it queues. The owner can review the schedule before Phase 5 fires.

### Phase 5 — Publish + Monitor
**Agents:** Publisher (per-platform), Podcast Publisher, Email Publisher, Engagement Monitor
**Outputs:** Live posts, metrics dashboard updates

Engagement Monitor runs continuously for 7 days post-publish; results flow into `~/.openclaw/data/engagement/<run-id>.json`.

---

## QC gates (the 6 QC agents)

Per N5, QC agents are **always different sub-agents than the producers**. They fire between phases:

| Gate | QC agent | Fires after | Blocks if |
|------|----------|-------------|-----------|
| Grammar | Grammar QC | Phase 2 (writer) | Score < 8.5 |
| Fact-check | Fact-Check QC | Phase 2 (writer) | Any claim unsourced |
| Visual | Visual QC | Phase 2/3 (image + video) | Brand-alignment fail |
| Compliance | Compliance QC | Before Phase 5 | Any legal/brand flag |
| Performance | Performance QC | Phase 3 | SEO score < threshold |
| Final | Final QC | Right before publish | Composite < 8.5 |

Max 5 retry loops per gate (N6). Loop 6 → escalate to owner via Telegram.

---

## How to trigger this skill

### Single-topic cycle:

```bash
bash ~/.openclaw/skills/35-social-media-planner/scripts/run-publishing-cycle.sh \
  --topic "How to delegate to AI without losing control" \
  --platforms "linkedin,medium,x,wordpress" \
  --schedule "auto"
```

### Recurring (cron-driven, e.g., weekly):

```bash
0 9 * * 1 bash ~/.openclaw/skills/35-social-media-planner/scripts/weekly-batch.sh
```

The weekly batch reads `~/.openclaw/config/content-calendar.json` and runs the 5-phase cycle for each scheduled topic.

### From the dashboard:

The Marketing department in the dashboard has a "Publish" button on each campaign. Clicking it queues a cycle for this skill.

---

## Platform-specific gotchas

| Platform | Cheat-sheet |
|----------|-------------|
| WordPress | Uses XML-RPC. Confirm `WP_XMLRPC_URL` in `.env`. References: `references/wordpress.md` |
| Medium | One post per day cap. Publisher auto-rate-limits. |
| Substack | Email-out happens server-side; we only publish the post. |
| LinkedIn | Article API requires a verified Business Page token. |
| GHL blog | Posts via the LeadConnector API. Respect daily quota — pre-check via `~/.openclaw/scripts/ghl-quota-check.sh` first (see cron-prompt RULE 18). |
| YouTube | Video Producer's output must be H.264 / AAC. Specs in `video-specs.json`. |
| X / Twitter | Thread mode: posts longer than 280 chars are auto-threaded. |
| Facebook | Page token only; personal profile posting is not supported. |

---

## Failure modes and recovery

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Image Generator errors on every prompt | Image model in `image-model.json` deprecated | Update the config to a current model (see N1 — non-Anthropic only) |
| Video Producer hangs at "encoding" | FFmpeg missing or wrong codec | `ffmpeg -version`; install if missing; verify codec in `video-specs.json` |
| Final QC keeps failing for "brand voice mismatch" | `SOUL.md` voice profile drifted | Re-read SOUL.md in the Strategist agent; do not patch in the writer |
| GHL post returns 429 | Daily quota exhausted | Stop, check quota, wait until reset clock (see cron-prompt RULE 18) |
| Posts publish but engagement is 0 | Wrong audience hour from `social-cadence.json` | Re-read cadence; A/B test alternate slot |

---

## When to invoke this skill

**Always:**
- Owner asks for a post / video / newsletter
- Calendar watcher fires (recurring schedule)
- Campaign in the dashboard transitions to "Publish" state

**Never:**
- For ad copy (that's Skill 36 — Paid Ads)
- For one-off internal memos (those go via Slack/Telegram, not the publishing pipeline)
- When any QC gate above is open from a previous cycle (resolve first)

---

## Cross-references

- `SKILL.md` — agent roster and key principles
- `INSTALL.md` — one-time setup
- `QC.md` — runtime QC rubric
- `references/<platform>.md` — per-platform API specifics
- Skill 36 — Paid Ads counterpart
- Skill 22 — persona pipeline (the brand voice persona is consumed by the Strategist)
- AGENTS.md `## 🔴 N1–N27` — non-negotiables governing this pipeline

---

*End of INSTRUCTIONS.md for Skill 35.*
