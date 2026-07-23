# Social Media Planner / Content Publishing Engine — Execution Instructions

**Version:** v10.13.0 (closes Audit Phase 12 — complete-answer playbook for owner scope questions)
**Skill:** 35-social-media-planner (a.k.a. Content Publishing Engine)
**Status:** Required runtime guide. Referenced from `SKILL.md` as part of the TYP read-order.

This is the **execution guide** for the 15+6 agent content publishing pipeline. `INSTALL.md` covers one-time setup; `SKILL.md` describes purpose. **This file covers how an agent actually runs a publishing cycle.**

---

## What this skill does

Orchestrate 15 production agents + 6 QC agents to research, create, produce, schedule, and publish content across every social channel the client has connected in GHL Social Planner. Also produces a weekly blog post, HTML email newsletter, and podcast episode (if Fish Audio / Skill 30 is configured).

**Primary GHL Social Planner channels** (the agent publishes to all that are connected):
Facebook (feed posts + carousels + Stories/Reels), Instagram (feed posts + Reels + carousels + Stories), LinkedIn (feed posts + PDF carousels), X/Twitter, TikTok, Pinterest, Google Business Profile.

**Content types produced every week**: daily social posts for all enabled platforms, Thursday carousels, short-form videos/Reels, unique comments with the client's action link (1-2 min after every post), blog post (Day 7), HTML email newsletter (Tuesday), podcast episode (if Fish Audio configured — gracefully skipped otherwise).

**Optional add-on channels** (direct integrations, never required): WordPress, Medium, Substack, YouTube.

The exact enabled platform set is determined at runtime by a live GHL connected-accounts query — never assumed from a fixed list.

The skill is **variable-driven** — every credential, URL, brand voice, and image-model setting is pulled from existing files. **Never hardcode a brand name, a domain, or a credential.**

---

## Owner scope question — LIVE CHECK MANDATORY

When an owner asks "what does my planner do?", "what platforms does it update?", "how do I use it?", or any similar scope/capability question:

1. **Run `check-social-connections`** (see section below) before answering — this is NOT optional for scope questions.
2. **Answer with the full picture**: list every enabled channel (from the live query), all content types produced, how to trigger a run, and the Saturday theme prompt schedule.
3. **Never answer from memory or a fixed generic list** — omitting a connected platform (such as Instagram or TikTok) because it was not in a memorized list is a BANNED failure.
4. **Include all required answer elements** (see SKILL.md Owner Q&A Playbook): enabled platform list, content-types statement, scope statement, how-to-trigger, and optional-add-ons note.

A scope answer that omits any platform shown in the live query result, or that lists only a partial set of content types, FAILS QC.

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
| API keys (GHL, WordPress, Medium, etc.) | `~/.openclaw/secrets/.env` |
| Platform URLs, location IDs | `~/.openclaw/secrets/.env` (e.g., `GOHIGHLEVEL_LOCATION_ID`) |
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
0. (Before image/video generation) Agnes vs. Kie.ai choice — if the client has BOTH Agnes (Skill 63/64)
   AND Kie.ai installed, offer the owner a choice: "I see you have Agnes. Because you have Agnes,
   would you like to use Agnes to create your videos and images, or would you prefer to stick with
   Kie.ai?" Route all generation calls based on the answer. If only one provider is installed, skip.
   See playbook.md Section 8 "Step 0 — Agnes vs. Kie.ai choice".
1. Writer drafts → Editor refines
2. Image Prompt Engineer writes prompts → Image Generator produces images
3. (If video) Video Script Writer drafts → Audio Generator voices it → Thumbnail Designer makes the preview
```

**Image Prompt Engineer — mandatory pre-write + pre-generation contract (P3-05, steps 7/9):**
Before writing ANY image prompt, load and merge the applicable avoid-list entries from
`45-design-intelligence-library/library/_system/NEGATIVE-PROMPTING-SOP.md` (universal
baseline) and `45-design-intelligence-library/library/social-media-designs/_RULES.md`
(category rules — ratios, hard rules, model routing). This is a load-BEFORE-write contract,
not a post-hoc check. Then, before the Image Generator submits ANY prompt, it MUST clear
`scripts/pregen_prompt_gate.py check` (playbook.md Section 8a) — ratio/pixel spec, brand
colors, merged avoid-list, verbatim Section-18 copy, and the brand-safety clause are all
required (exit 3 if any is missing); every text-overlay prompt MUST route to Ideogram V3
DESIGN, never Nano Banana (playbook.md Section 8; exit 6 if misrouted). A gate-failed prompt
is fixed and re-run, never generated. If the week's image asset instead comes from the
Graphics department, the Image Generator step is REPLACED by the Section 19a input-quality
gate: reject any graphics-department asset lacking a SOP-GIP-02 QC receipt >= 8.5.

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

## Command Center (Kanban) — operator visibility

`run-publishing-cycle.sh` advances a single Command Center card so operators can watch each run move across the board (HTTP API only — never the `.db`):

- **Cycle start** → the script creates one task (with a description so the Triad gate accepts it out of backlog) and PATCHes it to **in_progress** (`updated_by_agent_id=skill35-cycle`).
- **Hand-off to the orchestrator** → the script PATCHes the same task to **review**.
- **review → done** is promoted by the independent QC auto-scorer / department QC agent, NOT by this script. The builder never self-grades (the QC gate, N5) — the script never sets `done`.

Every Command Center call is **fail-soft**: if `MC_API_TOKEN` is unset or the board (`${MISSION_CONTROL_URL:-http://localhost:4000}`) is unreachable, the run logs `Command Center skipped` and finishes exactly as before (manifest + hand-off file, exit 0). The token is read from `$MC_API_TOKEN` or `~/command-center/app/.env.local`, and is never printed. This board update is operator-only — never client-facing chatter.

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

## Reporting connection status AND scope — LIVE GHL CHECK ONLY (no guessing)
Before you tell the owner which platforms are or are not connected, AND before you answer any question about what the planner does / what it updates / how to use it, you MUST run a LIVE query of their GHL Social Planner connected accounts (via the GHL API for the client's location). You may NOT say "connected" or "not connected" for any channel without that live result. You may NOT answer a scope/capability question with a fixed memorized list — that is exactly how a connected platform (Instagram, TikTok, Pinterest, Google Business Profile) gets omitted from the answer.

Reporting connection status OR skill scope from an assumption, from a memorized platform list, from the absence of a direct-platform token in the vault, or from memory is a BANNED failure (it is exactly the mistake that told a client only "8 platforms: WordPress, Medium, Substack, LinkedIn, GHL blog, YouTube, X/Twitter, Facebook" when their GHL Social Planner had Instagram, TikTok, Pinterest, Facebook carousels, and more connected and active).
- GHL Social Planner is the PRIMARY publishing path. The client connects their social accounts inside GHL, and you publish through GHL. ONE connected channel is enough to start. The client does NOT need all platforms.
- The direct-publish destinations (WordPress, Medium, Substack, LinkedIn, YouTube, X/Twitter, Facebook, email newsletter) are OPTIONAL add-ons for posting outside GHL. They are NEVER requirements, and their absence NEVER blocks Skill 35.
- Fish Audio / podcast (Skill 30) is OPTIONAL too. Skill 35 runs fully without it, it just skips podcast production.
- Run the check-social-connections step (the live GHL query) at status time, every time, and report only what it returns.

### check-social-connections — the live GHL query to run

When reporting connection status, run this live query and use ONLY its output. Try the highest tier available — **Tier 0 (Skill 44 `caf`) first**, then MCP, then direct API:

**If Skill 44 (Tier 0 CLI) is installed (PRIMARY):**
```bash
# List connected Social Planner accounts via the Convert and Flow CLI (Tier 0).
# NOTE: --json is a GROUP-level flag and MUST precede the subcommand
# (caf reads --json on the top-level group; "caf social accounts --json" errors).
caf --json social accounts
# Schedule a post (Tier 0). caf's safety gate REFUSES every write unless an
# approval token is present, so scope an approval token to THIS social-post call:
#   CAF_APPROVAL_TOKEN="skill35-social-approved" \
#     caf social create-post --account-id <id> --text '...' [--media-url <u>] [--schedule <iso8601>]
# Preview without sending: caf --dry-run social create-post --account-id <id> --text '...'
```

**If Skill 44 is absent but Skill 36 (GHL MCP) is installed (`ROUTING_MODE=mcp-first`):**
```bash
# Query connected Social Planner accounts via the community MCP. The MCP HTTP
# transport speaks JSON-RPC ("tools/call"), NOT a flat {"name","arguments"} body,
# and the account tool is get_social_accounts. Confirm the exact tool name and
# endpoint path against your installed community MCP manifest before relying on it.
MCP_URL=$(openclaw config get env.vars.GHL_COMMUNITY_MCP_URL 2>/dev/null | tr -d '\n' | sed 's|/$||')
curl -sS -m 15 -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_social_accounts","arguments":{}}}' \
  | python3 -m json.tool
```

**If Skill 36 is NOT installed (`ROUTING_MODE=direct-api`):**
```bash
# Query each major platform directly against the GHL Social Planner API
. "$HOME/.openclaw/secrets/.env"
for PLATFORM in facebook instagram linkedin twitter google_business tiktok; do
  echo "--- $PLATFORM ---"
  curl -sS -m 10 \
    -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
    -H "Version: 2021-07-28" \
    "https://services.leadconnectorhq.com/social-media-posting/oauth/$GOHIGHLEVEL_LOCATION_ID/$PLATFORM/accounts" \
    | python3 -m json.tool
done
```

Report the exact platforms returned by the live query. If the query returns empty results for a platform, say so — do NOT assume the platform is disconnected without confirming the query succeeded (200 OK with an empty list is different from a 403 scope error).

---

## Weekly trigger — CRON, not heartbeat (enforcement)
The weekly content-theme question and the weekly social-planning run MUST be driven by a hard cron, NOT the heartbeat checklist. Heartbeat timing drifts and silently skips the weekly prompt (this is exactly why a client's Saturday theme question never fired). At activation, install a weekly cron (default Saturday 8:00 AM client-local time) that (a) asks the owner the content-theme question and (b) runs the weekly social plan, backed by a state field so it is idempotent and catches up if a fire is missed. Do NOT rely on heartbeat prose for any weekly trigger.

The cron is installed as part of the activation step below. INSTALL.md Step 9 directs the installer to remove any Saturday theme-request block from the client's live HEARTBEAT.md — that block MUST NOT exist because the agent acts on heartbeat prose every tick. The cron is the sole enforcement mechanism.

### Activation — install the weekly theme cron (AUTOMATED via script)

> **Do NOT run inline bash here.** The cron is now registered by the bundled script called from INSTALL.md Step 9. This ensures it is fail-loud, deduped, and QC-asserted automatically during install. Manual inline invocation is kept only as a break-glass reference.

INSTALL.md Step 9 runs:

```bash
bash ~/.openclaw/skills/35-social-media-planner/scripts/register-weekly-cron.sh
```

The script handles all of the following automatically:
- Idempotency: skips if a healthy `main`-target `skill35-weekly-theme` entry already exists.
- Deduplication: deletes stale/erroring duplicate entries before registering.
- Hard-fail: exits non-zero on any registration failure (installer must not proceed to Step 10).
- Post-registration QC: asserts exactly 1 entry, `sessionTarget=main`, schedule `0 8 * * 6`.
- Marker path: `~/.openclaw/data/skill35/weekly-theme-last-run.json` (persistent, not /tmp).
- Model: cheap/free (flash or free OpenRouter fallback) — never a metered pro model.
- `sessionTarget=main` (isolated + channel-deliver is rejected by the gateway).

**Break-glass only** (use if the script itself is unavailable on the install path):

```bash
CRON_NAME="skill35-weekly-theme"
if openclaw cron list 2>/dev/null | grep -q "$CRON_NAME"; then
  echo "cron $CRON_NAME already registered — skipping"
else
  openclaw cron add \
    --name "$CRON_NAME" \
    --cron "0 8 * * 6" \
    --agent main \
    --session-target main \
    --light-context \
    --message "Skill 35 weekly theme trigger. Check ~/.openclaw/data/skill35/weekly-theme-last-run.json — if weekISO matches current ISO week, skip. Otherwise: ask the owner their content theme for the week, wait up to 1 hour, default to evergreen if no reply. Run the weekly social plan. Write the marker file after completion." \
    && echo "registered cron: $CRON_NAME (0 8 * * 6 — Saturdays 8 AM)" \
    || { echo "ERROR: openclaw cron add failed"; exit 1; }
fi
```

Do NOT write a `cron.jobs` JSON block — it does not validate on OpenClaw 2026.5.27+.
Do NOT use `--announce --channel last --best-effort-deliver` with `sessionTarget=main` — the gateway rejects channel-delivery config on main-target crons (confirmed on a client box 2026-06-15).

---

## Reusable guard pattern for any recurring real-work task in HEARTBEAT.md

**Rule:** Any task that must fire on a specific cadence (daily, weekly, monthly) and does real work (calls an API, runs a pipeline, sends a message) MUST use a hard cron, NOT a heartbeat prose entry. If — after careful review — a task absolutely must live in HEARTBEAT.md rather than a cron, it MUST include BOTH guards:

1. **Day-of-week / time gate** — check with `date` before doing work
2. **Idempotency marker** — a file/key that proves this period's fire already ran

```bash
#!/usr/bin/env bash
# ── HEARTBEAT.md recurring real-work guard pattern (fleet-wide template) ──
# Copy this pattern for any HEARTBEAT.md task that must NOT fire on every tick.
# Replace DOW, MARKER_PATH, and the "do real work here" block.

DOW=6                          # 1=Mon … 7=Sun (date +%u)
MARKER_PATH="$HOME/.openclaw/data/<skill>/weekly-task-last-run.json"
PERIOD_KEY="$(date +%Y-%U)"   # ISO year + week number (change to %Y-%m-%d for daily)

# Guard 1: day-of-week
if [ "$(date +%u)" != "$DOW" ]; then
  echo "HEARTBEAT guard: not Saturday (day=$(date +%u)) — skip" && exit 0
fi

# Guard 2: idempotency (already ran this period?)
if [ -f "$MARKER_PATH" ] && python3 -c "
import json, sys
d = json.load(open('$MARKER_PATH'))
sys.exit(0 if d.get('period') == '$PERIOD_KEY' else 1)
" 2>/dev/null; then
  echo "HEARTBEAT guard: already ran for period $PERIOD_KEY — skip" && exit 0
fi

# ── Do real work here ────────────────────────────────────────────────────────
# ...

# ── Write idempotency marker ─────────────────────────────────────────────────
mkdir -p "$(dirname "$MARKER_PATH")"
python3 -c "import json; json.dump({'period': '$PERIOD_KEY', 'ts': __import__('datetime').datetime.utcnow().isoformat()}, open('$MARKER_PATH', 'w'))"
echo "HEARTBEAT guard: work done for period $PERIOD_KEY — marker written"
```

**Preferred alternative:** register an `openclaw cron add` job instead. Crons fire on a hard schedule, never on every heartbeat tick, and do not pollute HEARTBEAT.md with executable prose.

See also: `docs/HEARTBEAT-GUARD-PATTERN.md` (fleet-wide reference).

---

## Cross-references

- `SKILL.md` — agent roster and key principles
- `INSTALL.md` — one-time setup
- `QC.md` — runtime QC rubric
- `references/<platform>.md` — per-platform API specifics
- Skill 36 — Paid Ads counterpart
- Skill 22 — persona pipeline (the brand voice persona is consumed by the Strategist)
- Skill 45 (`45-design-intelligence-library`) — owner of the negative-prompting SOP and the social-media-designs category rules every image prompt this skill writes MUST load before authoring (playbook.md Section 8b); Skill 45's graphics-department deliverables are gated into this skill's pipeline via the Section 19a input-quality gate (SOP-GIP-02 receipt >= 8.5, `scripts/pregen_prompt_gate.py --asset-source graphics-department`)
- AGENTS.md `## 🔴 N1–N27` — non-negotiables governing this pipeline

---

*End of INSTRUCTIONS.md for Skill 35.*
