# AutoWebinar Behavioral Branching Sequence (4-Path Watch-Duration Segmentation)

- **id:** `autowebinar-behavioral-branching`
- **Category:** multichannel-automation
- **Aliases:** AutoWebinar Follow-Up · Evergreen Webinar Follow-Up · Watch-Duration Segmented Sequence · No-Show Sequence · Replay Follow-Up · Watched Did Not Buy Sequence
- **Source:** Funnel Hacker's Cookbook — AutoWebinar Funnel (Event Funnel Recipe #3). Supporting: BRUNSON-FUNNEL-LIBRARY Entry #16, Marketing Secrets Blackbook Secret #65 + #66, Lead Funnels Swipe File (channel stack).

> "They are then emailed links to indoctrination pages where you can get them excited about the training they either are about to get on, or just completed. After their presentation time has passed, they are then emailed links to a replay room where they have one last chance to watch the webinar." — Funnel Hacker's Cookbook

> "Watch-time tracking triggers segmented follow-up sequences (registered, watched to end, left early, no-show). Brunson notes two of his automated webinars each produced over $1 million." — BRUNSON-FUNNEL-LIBRARY Entry #16

## What it is
The AutoWebinar Funnel runs a proven live webinar recording 24/7 — registrants choose a broadcast time, watch (or don't), and are automatically sorted into one of four behavioral paths based on watch duration. Each path gets different messaging. The no-show and left-early paths drive replay visits. The watched-no-buy path handles objections, then applies urgency. The buyer path stops all sales messages immediately and routes to onboarding.

## TRIGGER
- **What starts it:** Webinar registration form submit.
- **Path detection:** Watch-time data from the broadcast room triggers tags that route each contact to their specific follow-up path.
- **Re-entry guard:** Tag `webinar-registered` NOT present.

## CHANNELS
Email (primary across all 4 paths) · SMS (pre-webinar reminders + replay urgency nudges) · Facebook Messenger (replay link + offer nudge, if subscribed)

---

## THE 4 PATHS

### PATH A — Registered / No-Show
**Signal:** `webinar-attended` NOT present after broadcast window closes.

| Step | Delay | Channel | Content |
|------|-------|---------|---------|
| A1 | After broadcast | Email | "You missed it — here's the replay" — curiosity tease + replay link + replay deadline |
| A2 | +1h (if replay not visited) | SMS + Messenger | Quick nudge: "replay link here" |
| A3 | +24h | Email | Replay urgency — replay comes down soon |
| A4 | +48h (after replay expires) | Email | "Replay is down — here's how to still get [result]" — direct offer CTA |

**Subject angles:**
- A1: `You missed it — here's the replay`
- A3: `Replay comes down [tomorrow / at midnight] — here's the link`
- A4: `Replay is down — but here's how to still get [result]`

**Body framework for A1:**
- Acknowledge missed it (warm, no guilt)
- Tease what was covered → build curiosity
- Direct replay link with stated window
- Note SMS/Messenger mirror coming

---

### PATH B — Left Early
**Signal:** `webinar-left-early` tag set by watch-time webhook (attended but dropped before offer reveal point).

| Step | Delay | Channel | Content |
|------|-------|---------|---------|
| B1 | Within 1h of broadcast end | Email | Warm personal check-in: "You disappeared before the best part" |
| B2 | +2h (if email not opened) | SMS + Messenger | "You dropped off before [key moment]. Quick replay link: [link]" |
| B3 | +24h | Email | "Here's what happened after you left" — FOMO, reveal what they missed |
| B4 | +48h | Email | "Skip the replay — here's [offer] directly" (if no purchase yet) |

**Subject angles:**
- B1: `Everything okay? You disappeared before the good part`
- B3: `Here's what happened after you left [webinar name]`
- B4: `Skip the replay — here's [offer] directly`

**Body framework for B1:**
- "I noticed you jumped off before we got to the best part."
- Name what they specifically missed (key insight / offer reveal)
- No guilt — genuine curiosity
- Replay invite with link to "jump back in from where you left off"

---

### PATH C — Watched to End / Did Not Buy
**Signal:** `webinar-watched-full` tag present AND `purchased-[offer-id]` NOT present 1h after broadcast ends.

| Step | Delay | Channel | Content |
|------|-------|---------|---------|
| C1 | Within 1–2h of broadcast end | Email | Objection-handle email: "Still thinking about it? Here's what I should have mentioned" |
| C2 | +30–60 min (if C1 not clicked) | SMS + Messenger | "Did you have a question? Reply here or grab it here: [link]" |
| C3 | +24h | Email | Third-person testimonial / case study with specific results |
| C4 | +48h | Email | Urgency / closing email — real deadline stated plainly |

**Subject angles:**
- C1: `Still thinking about it? Here's what I should have mentioned`
- C3: `What [customer name] said after [achieving result]`
- C4: `The [offer name] offer closes [tonight/tomorrow] at [time]`

**Body framework for C1:**
- Acknowledge they stayed through the whole thing (respect their time)
- Name the most common objections head-on: "when someone watches the whole thing and doesn't grab [offer], it usually comes down to one of these..."
- Handle 2–3 objections with social proof, guarantee, or reframe
- CTA to offer with deadline

**Body framework for C4:**
- State real deadline plainly
- Consequence of not acting
- Final CTA
- P.S.: "If you have a question first, just reply — I'll personally respond."

---

### PATH D — Purchased (at any point — during or after webinar)
**Signal:** `purchased-[offer-id]` tag added.

**Actions (fires immediately):**
1. Add `purchased-[offer-id]`
2. Remove from all retargeting audiences for this offer
3. Stop all Path A / B / C sequences immediately
4. Send purchase confirmation email + access/delivery details
5. Optional SMS: "You're in! Check your email for access details."
6. Start buyer onboarding workflow

---

## PRE-WEBINAR INDOCTRINATION SEQUENCE
Fires between registration and the broadcast window to prime the registrant to show up and be in the right mindset (per FHC AutoWebinar Funnel description):

| Timing | Channel | Message |
|--------|---------|---------|
| Immediately on registration | Email | Confirmation — access link, date/time, what to expect |
| 24h before broadcast | Email | Teaser — why this training matters; key insight preview |
| 1h before broadcast | Email + SMS | "Starting in 1 hour — here's your link: [broadcast_room_url]" |
| 5 min before broadcast | SMS (if available) | "Starting in 5 min — click here: [broadcast_room_url]" |

---

## COPY PERSONA + SCRIPT

| Path | Tone | Approach |
|------|------|----------|
| A — No-Show | Friendly, zero guilt | "You missed it — here's your replay." Curiosity tease of what was inside. |
| B — Left Early | Warm personal check-in | "You disappeared before the best part." FOMO without blame. |
| C — Watched / No Buy | Objection-handle → proof → urgency | Logic close (C1–C3) before fear close (C4). Acknowledge their time investment. |
| D — Buyer | Celebration and delivery | Fast confirmation, access delivery, onboarding. Stop all sales messaging immediately. |

## FLEXIBILITY — Core Principle

> This template is a **GUIDE and a RESOURCE, never a rule or requirement.** It must not dominate the user's desire.

| Mode | When it applies | What the system does |
|------|----------------|----------------------|
| **1 — Explicit desire** | User wants a custom webinar follow-up | Do exactly that. Template is reference only. |
| **2 — User is unsure** | User doesn't know how to follow up after the webinar | Suggest the 4-path structure; explain why each segment needs different messaging; let user decide. |
| **3 — Just do it** | "Build the autowebinar follow-up" | Build all 4 paths with detection logic and timing as described. |

Watch-duration threshold, replay window, number of emails per path — all are configurable recommended defaults.

---

## GHL BUILD (Skill 44 — Convert & Flow Operator)

**Dependencies first:**
- **Tags:** `webinar-registered`, `webinar-attended`, `webinar-left-early`, `webinar-watched-full`, `webinar-replay-visited`, `purchased-[offer-id]`, `messenger-subscribed`, `sms-subscribed`
- **Custom fields:** `webinar_register_date (date)`, `webinar_watch_duration_pct (number)`, `webinar_broadcast_time (datetime)`
- **Custom values:** `{{broadcast_room_url}}`, `{{replay_room_url}}`, `{{offer_page_url}}`, `{{replay_expiry_date}}`, `{{webinar_offer_name}}`

**Workflow architecture:**
1. Trigger: Form Submitted (registration page) → Add `webinar-registered`; Set `webinar_register_date`
2. Email `WB-01 Registration Confirmation` (immediate)
3. Wait until 24h before `webinar_broadcast_time` → Email `WB-02 Tomorrow Reminder`
4. Wait until 1h before `webinar_broadcast_time` → Email + SMS `WB-03 / WB-S01 Join in 1 Hour`
5. After broadcast window: branch on watch tags → route to Path A, B, or C workflow; purchase event → Path D

**Watch-time tags** (`webinar-attended`, `webinar-left-early`, `webinar-watched-full`) should be set via GHL webhook from the webinar platform. If no native integration, approximate with broadcast-room page-visit tracking.

**Templates:** Email WB-01..WB-12 in GHL Email Builder; SMS WB-S01..WB-S03; Messenger WB-M01..WB-M02.

**Skill 44 notes:** Set `order` + `parentKey` on every node before first save. Purchase interrupt at any point removes contact from all active sequences and starts buyer onboarding.
