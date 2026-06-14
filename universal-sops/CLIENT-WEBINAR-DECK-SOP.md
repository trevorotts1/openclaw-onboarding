# CLIENT WEBINAR DECK SOP
**Standard Operating Procedure: Branded Webinar / Slide Deck, End-to-End**
**Version 2.4 (2026-06-14)**
**Audience:** any client's OpenClaw agent (lead agent + sub-agents). This document is self-contained. The executing agent needs NOTHING else to take a client from a blank conversation to a finished, QC-passed, branded, pitch-correct PowerPoint.
**Provenance:** generalized from the proven Lyric Hawkins "Enrollment on Autopilot" run (75 slides, final QC 9.42). Pitch mechanics are drawn from Alex Hormozi's $100M Offers and $100M Leads, the flow, archetypes, ladder choreography, and exemplar prompt are extracted from the actual Lyric run assets (75 prompts, final deck, execution runbook), and the pitch doctrine in Section 4.3 is transcribed from the operator's live teaching sessions. All client-specific values are DISCOVERY VARIABLES. Nothing client-specific is hardcoded.

---

## 0. PURPOSE AND PIPELINE MAP

Take a client from "I want a webinar deck" to a delivered PPTX through this exact pipeline:

```
STEP 0   Create local + GHL media library folders        (always first)
PHASE A  Discovery interview (3 to 10 adaptive questions)
PHASE B  Slide math: duration to slide count cap
PHASE 1  Write every slide's copy (Hormozi structure + price drop)
PHASE 1Q Internal copy QC gate (agents, >= 8.5)
PHASE 1A OWNER APPROVAL GATE (human says yes before any prompt is written)
PHASE 2  Write one image prompt per slide (1,500 to 15,000 chars)
PHASE 3  Prompt QC gate (5 to 10 agents, >= 8.5, auto-loop)
PHASE 4  Generate on Kie.ai gpt-image-2 (rate-capped, polled, loop-guarded)
PHASE 5  Image QC gate (>= 8.5, auto-loop, passes upload to GHL immediately)
PHASE 6  PPTX assembly, final deck QC, speaker notes, delivery
```

**Non-negotiables (memorize before starting):**
- Media library folders (local + GHL) are created FIRST, before anything else.
- Words before prompts. Prompts before generation. Prompt QC gates generation. Image QC gates assembly. The OWNER approves the slide copy before a single prompt is written.
- Image platform and model: **Kie.ai running the GPT Image 2 family only**, pinned in the MODEL MANIFEST (9.0) and declared to the operator at echo time. No other image model in any situation unless the OPERATOR explicitly authorizes it in writing. A model outage means PAUSE and escalate, never substitute.
- Rate cap: never more than **20 image requests per 10 seconds (2 RPS)**. This is a REQUEST-rate cap, not a token cap.
- One big idea per slide. Slides must be legible from the back of the room.
- Client brand colors on a **WHITE BASE**. No dark-styled images ever unless the client explicitly asks (`DARK_OK = true`).
- 16:9 always. 2K quality unless the client indicates otherwise.
- All QC thresholds: **>= 8.5 passes.** Anything below 8.5 loops back through revision AUTOMATICALLY, without bothering the owner. Only >= 8.5 work ever reaches the owner or the GHL library.
- Polling loop guard: poll a maximum of **100 times** per generation run. Never loop forever.
- Client's OWN API keys only (KIE, Ollama Cloud, OpenRouter, GHL, Drive), from the client's own box. Never another client's keys, never the operator's keys.
- No em dashes anywhere, in any output, ever. The em dash is a dead giveaway of unedited AI output; QC auto-fails it on sight.
- **NEVER DIE SILENTLY.** Any hiccup (Kie.ai tokens/credits exhausted, a model unavailable, GHL auth failing, a stalled loop) is escalated to the operator IMMEDIATELY. A run that quietly stops is worse than a run that loudly fails.
- The deck has a HOOK and it is sung on a SCHEDULED cadence: 3 to 4 dedicated hook slides on a ~30-min deck plus proof-earned refrains, floor 7 total on a 45+ deck, HARD CEILING of roughly 1 occurrence per 6 slides and never two consecutive slides (Section 4.3, rule 1). A deck without a singing hook is not done; neither is a deck that stamps the hook on every slide.
- **Ten named presentation components are REQUIRED and QC-gated in every deck (Section 4.4): the Promise, the Hook, Case Studies / "who says so other than you", the Wall of Wins, One Big Idea Per Slide, the Guarantee, the Scarcity Factor, the Story Arc (short-term fix vs long-term identity), the Gradual Price Ladder, and the checklist-is-a-list-of-promises discipline. Each is a mandatory element with an explicit QC gate; a deck missing any one of them is not done.** A multi-idea slide auto-fails; a zero-proof deck fails; a missing guarantee, scarcity beat, wall of wins, or story arc fails at copy QC and final-deck QC.

---

## 1. MODEL ROUTING AND FALLBACK CHAIN

| Role | Primary | Fallback 1 | Fallback 2 |
|------|---------|------------|------------|
| Slide copy, prompts, orchestration | `ollama/kimi-k2.6:cloud` (Kimi 2.6, Ollama Cloud) | DeepSeek v4 Pro (the operator-approved alternate writer; lead agent picks per this SOP and records the choice) | Same models via OpenRouter |
| QC agents (copy QC, prompt QC, image QC, final deck QC) | `ollama/minimax-m3:cloud` (Minimax 3 preferred) | Minimax 2.7 if no M3 on the box | **DeepSeek v4 Flash** (final fallback; OpenRouter route acceptable) |
| Image generation | **Kie.ai GPT Image 2** per the MODEL MANIFEST (9.0): `gpt-image-2-image-to-image` with references, `gpt-image-2-text-to-image` without | NONE mid-run. | Version upgrades / model changes: operator updates the manifest in writing. |

**Rules:**
- Ollama Cloud is preferred for text models. Verify it actually works with one live test turn before the run: `:cloud` model IDs require `models.providers.ollama.baseUrl = https://ollama.com` plus the client's `OLLAMA_API_KEY`. A local `127.0.0.1:11434` baseUrl with `:cloud` IDs will ECONNREFUSED.
- If Ollama Cloud is unavailable, use the OpenRouter version of the SAME models with the client's OpenRouter key. The text-model fallback chain never applies to the image model.
- If the latest Minimax is newer than M3 on the client's box, use the latest. Record the exact model IDs used in `working/checkpoints/models_used.json`.
- Search ALL of the client's env stores before declaring a key missing: `~/.openclaw/workspace/.env`, `~/clawd/secrets/.env`, `openclaw.json` env.vars, and the running gateway process env.
- Long generation and poll loops run DETACHED with checkpoint files. No agent sits open babysitting a poll loop.

---

## 2. STEP 0: CREATE THE MEDIA LIBRARY (THE FIRST ACTION, ALWAYS)

Before the discovery interview, before slides, before anything, create the landing zones. If these folders do not exist, passed work gets lost.

1. **Local project workdir** on the client's box:
   `~/webinar-decks/<client-slug>/<deck-slug>/<YYYY-MM-DD>/`
   (VPS clients: `/data/.openclaw/workspace/webinar-decks/<client-slug>/<deck-slug>/<YYYY-MM-DD>/`. Always a fresh dated dir. Never reuse or overwrite a previous run's dir. Never flatten or skip the date level.)
2. Inside it:
   ```
   media-library/           passed images land here (the deliverable folder)
   working/prompts/         per-slide prompt files
   working/renders/         raw downloads from KIE (pre-QC)
   working/checkpoints/     task-id / poll / QC checkpoint JSONs
   working/qc/              QC reports
   working/copy/            slide copy drafts and approval records
   ```
3. **GHL media library folder** in the client's own GHL location: create a folder named `"<Client> <Deck> v<N>"`. Known issue: GHL folder creation via API has been broken before. If it fails, upload to Media Library root and rely on the naming convention to disambiguate. Log which path you took.
4. Mirror folder in the client's Drive if they use Drive.
5. Record all paths and IDs in `working/checkpoints/media_library.json`.
6. **Naming conventions (mandatory):**
   - Local files: `slide-01.png` ... `slide-NN.png` (zero-padded kebab-case). python-pptx reads these names for ordered assembly.
   - GHL remote names: `Slide 01 v<N>` ... `Slide NN v<N>` (zero-padded, human-readable).
   - Mixing these conventions up breaks assembly order. Set them here, enforce them at every phase.

Only when both landing zones exist do you proceed to Phase A.


### 2.1 STEP 0.5: SYSTEM CAPACITY ANALYSIS (size the agent fleet to the client's box, before dispatching anything)

Sub-agent counts in this SOP (writers, 5 to 10 QC agents, submission agent) are CEILINGS, not entitlements. Before Phase 1, the lead agent runs a quick capacity probe of the client's OpenClaw setup and records the plan in `working/checkpoints/capacity_plan.json`.

**The probe (60 seconds of checks):**
1. Box resources: total/free RAM, CPU cores, current load, free disk (`free -h`, `nproc`, `uptime`, `df -h`). On shared/oversubscribed VPS deployments, treat FREE memory at probe time as the budget, not the advertised total.
2. Model location: Ollama Cloud reachable with the client's key (one live test turn)? If models are CLOUD, sub-agents are I/O-bound and cheap locally. If any model runs LOCALLY on the box, concurrency collapses to what the RAM holds (usually 1 to 2 model instances).
3. Budget: Kie.ai credit balance vs the run's image budget (SLIDE_COUNT x 2 x ~$0.03 per image; a 75-slide deck budgets ~$4.50 ceiling). Ollama Cloud / OpenRouter token balance sanity check. **If tokens or credits will run out mid-run, tell the operator BEFORE starting, not after dying.**
4. Other tenants: is another client job or gateway process running hot on this box? Reduce the fleet accordingly.

**Fleet sizing defaults (cloud models, healthy box):**
| Free RAM at probe | Max concurrent sub-agents (total) | QC agents | Writer agents |
|---|---|---|---|
| under 4 GB | 4 | 3 | 1 (sequential batches) |
| 4 to 8 GB | 6 | 5 | 2 |
| 8 to 16 GB | 8 | 6 | 3 |
| over 16 GB | 10 to 12 | 7 to 10 | 3 to 4 |

- Local (non-cloud) text models: cap the entire fleet at 2 and run QC in sequential batches; escalate to the operator that the run will be slow.
- The submission agent is always exactly 1 regardless of fleet size (the rate cap depends on it).
- The watchdog cron (11.5) costs nothing and always runs.
- Speed expectations to set with the client (proven benchmarks): a 75-slide deck lands in roughly 90 minutes end to end; a 25-slide deck in 10 to 15 minutes; images cost about 3 cents each, so a full custom deck is cents to a few dollars in generation cost.

---

## 3. PHASE A: DISCOVERY INTERVIEW (3 TO 10 QUESTIONS, ADAPTIVE)

**FIRST-TIME ONBOARDING (the owner's first-run experience).** The trigger is CONVERSATIONAL: the owner says something like "I need a deck / a webinar / a pitch." The agent does NOT launch into a form. It meets the owner with "Let's brainstorm it together first," then runs the brainstorming buddy as FRIENDLY proactive Q&A (3 to 10 ADAPTIVE questions, NOT a 50-question dump). The brainstorm USES known business context rather than re-asking it (the governing rule below), offers the deliverable add-ons (the guide, the speech, the audio demo), and offers the STYLE BRANCH ("Do you have an existing deck or visual style to match, a reference deck to analyze, or should we create a signature style for you?"). Only after the brainstorm does it ECHO -> PRD -> checklist gate (Section 3.3), then proceed Phase A -> B. The owner sees a conversation and a confirmation, never a build that started before they said go.

**Rule: ask a MINIMUM of 3 and a MAXIMUM of 10 questions.** Before asking anything, check what the agent already knows (brand kit on file, prior decks, memory, GHL settings). NEVER ask a question whose answer is already known. Skip, confirm, or ask, in that order. Record every answer in `working/intake.json` and echo the full intake back to the client for confirmation before Phase 1. The intake also captures the deliverable scope and pacing: `WANT_AUDIO_DEMO` (y/n + voice/persona), `TARGET_WPM` (default 140), and `DELIVERABLE_SET` (deck only / +guide / +guide+speech / +audio), plus the style-branch answer (match / analyze a reference / create a signature style).

### 3.1 The question bank (pull from this, in priority order)

**Q1. THE GOAL (always ask).** "What is the goal of this presentation? What do you want people to DO at the end?" (Buy the offer, book a call, join the challenge, donate, enroll.) Variable: `GOAL`, `CTA_ACTION`.

**Q2. THE FEELING (always ask).** "When someone walks away from this webinar, how do you want them to FEEL?" (Capable and fired up, safe and understood, urgently behind, hopeful, seen for the first time.) Variable: `TARGET_FEELING`.

**Q3. THE TONE (ask unless tone is already on file).** Offer these seven named styles and let them pick one or blend two:
1. **Inspirational** (rise-up energy, possibility language, big vision)
2. **Tough Love** (direct, calls out excuses, "nobody is coming to save you")
3. **Challenger** (provokes, flips beliefs, "everything you were taught is wrong")
4. **Teacher / Authority** (calm expertise, frameworks, receipts)
5. **Storyteller** (narrative-first, emotional arc, testimony-driven)
6. **High-Energy Hype** (fast, loud, celebration energy, big numbers)
7. **Calm Premium** (understated, luxury, scarcity through quietness)
Variable: `TONE`.

**Q4. PRICE STRUCTURE (always ask).** "Do you want a gradual price drop (we walk the price down from a big anchor, the proven Lyric method) or a straight price (one price, stated once)?" If gradual: collect the full offer stack, each component's standalone value, the anchor, the final price, payment plan. If straight: collect the price and the value stack that justifies it. Variables: `PRICE_MODE` (`drop` | `straight`), `OFFER_STACK`, `PRICE_ANCHOR`, `FINAL_PRICE`, `PAYMENT_PLAN`.

**Q5. VIP LEVEL (always ask).** "Do you want a VIP or premium tier in this pitch?" If yes: what it includes, its price, and how many spots (real scarcity only). Variables: `VIP_TIER`, `VIP_PRICE`, `VIP_SPOTS`.

**Q6. DURATION (always ask).** "How many minutes is the presentation? (10, 15, 30, 45, 60, 90...)" Variable: `DURATION_MIN`. This drives the slide cap in Phase B.

**Q7. BRAND COLORS (skip if already on file).** Exact hex codes for primary, secondary, accent. Ask for the brand guide if one exists. Variables: `BRAND_PRIMARY`, `BRAND_SECONDARY`, `BRAND_ACCENT`.

**Q7a. THE HOOK SEED (ask whenever the client has language they already use).** "Is there one line you already say all the time, the thing you want them humming when they leave?" If they have one, it seeds `HOOK`; if not, Phase 1 derives it from the promise and the owner confirms it at the approval gate (Section 4.3, rule 1).

**Q8. LOGO (skip if already on file).** "Do you want your logo to appear on the slides?" If yes: highest-res transparent PNG plus a stable public URL (Kie image-to-image needs a URL; if only a file arrives, upload it to the client's GHL media library or Drive and record the URL). Variables: `LOGO_ON_SLIDES`, `LOGO_FILE`, `LOGO_URL`.

**Q9. AUDIENCE REPRESENTATION (always ask unless on file).** "Who is your audience, and how should people in the images break down?" Collect demographics WITH PERCENTAGES, for example: "70% African American women, 20% African American men, 10% mixed" or "100% women, diverse" or "no people at all." The percentage breakdown is enforced across the deck in Phase 2 (a 60-slide deck at 70/20/10 means people-slides are allocated in roughly that ratio). Variables: `AUDIENCE`, `REPRESENTATION_MIX` (list of {group, percent}).

**Q10. VISUAL MIX (always ask unless on file).** "Should your slides primarily feature people, some people, be typography-led, or a mix of both?" Options: `people-heavy` (people on ~60%+ of slides), `some-people` (~30%), `typography-led` (people only where proof demands it), `mix` (~45%). Variable: `VISUAL_MIX`.

**Supplementary (only if room remains under the 10-question cap and the answer is unknown):** style references or decks they admire (`STYLE_PREFS`); dark styling explicitly wanted? (`DARK_OK`, default false); existing assets to collect NOW (testimonials, screenshots, press logos, before/after numbers) (`PROOF_ASSETS`); anything else important to them, captured verbatim (`CLIENT_NOTES`).

### 3.2 Asset collection rule
Any testimonial, revenue number, screenshot, or press mention used in the deck comes from the client or is marked `[CLIENT TO SUPPLY]`. Collect `PROOF_ASSETS` during discovery so placeholders are rare. **Hard rule for assembly:** if a `[CLIENT TO SUPPLY]` placeholder is still unfilled at Phase 6, that slide is built WITHOUT the fabricated element (restructured by a quick copy revision), never with invented proof. Never fabricate.


### 3.3 THE ECHO PROTOCOL (gate between intake and Phase 1; mandatory)

The echo follows the friendly brainstorm (the conversational first-time trigger above): the brainstorm gathers only the unknowns and the add-on/style branches, then this echo proves the agent understood. Before any big project begins, the agent proves it understands the mission. After intake is confirmed:
1. **ECHO:** the agent echoes back, in its own words, what it understands the mission to be: the goal, the audience, the offer, the price mode, the tone, the hook direction, and what done looks like.
2. **PRD + CHECKLIST:** the agent produces a short PRD and its OWN checklist for the run. A checklist for an AI is a LIST OF PROMISES: before the agent ever says "I'm done," it walks its own checklist and verifies every promise was kept.
3. **IMPROVEMENT PASS:** the agent lists what it believes, based on everything it has learned (the SOP, the books, the sample deck), would improve the plan beyond what was asked.
4. **WAIT:** work does not start until the operator/client reviews the echo and says go. No echo approval, no Phase 1.

### 3.4 TWO OPERATING MODES (declare the mode in the echo)

**MODE A: FROM SCRATCH.** The full pipeline as written: discovery, slide math, copy, prompts, generation, assembly.

**MODE B: ENHANCEMENT (the client already has a deck).** The client hands over an existing presentation and the rule is absolute: **do not change their intent, do not change their words, do not change their methodology. Add on to, improve upon, never change.** The work in Mode B:
1. Analyze the existing deck against this SOP: flow, pitch structure, hook presence, pain coverage, proof density, cost-vs-value, one-big-idea compliance.
2. Report the gap analysis to the owner BEFORE touching anything (this is the Mode B echo): which slides split (one idea per slide), which pain points need their own slides, where the hook will sing, where light pitches weave in, where the ladder and the cost-vs-value math insert, what the missing slides are.
3. ADD slides: hook slides, pain slides, proof and white-paper slides, ladder slides, roadmap slides, quote slides, cost-vs-value slides. The client's original content slides keep their words verbatim (typo fixes only, flagged).
4. REDESIGN visuals to the premium standard (photography not emojis, archetype rotation, brand grammar) while the client's text content rides along unchanged.
5. The owner approval gate (1A) applies to the combined deck exactly as in Mode A. Everything downstream (prompts, generation, QC, assembly) is identical.

---

## 4. PHASE B: SLIDE MATH (DURATION DRIVES THE CAP)

**The governing concept: ONE BIG IDEA PER SLIDE.** Slides move fast (a webinar presenter changes slides every 35 to 60 seconds in the teaching sections and faster in the stack). The cap exists so every slide stays legible and the deck stays presentable in the time given.

**The canonical hierarchy stack (the default element stack on a teaching slide) is ONE big idea, expressed as kicker (optional) + headline + at most one supporting line.** The hook refrain and the italic tertiary line are NOT default stack elements on every slide; they appear only where scheduled (the hook on its cadence per Section 4.3 rule 1; the tertiary line only where a slide genuinely earns a third beat). Stacking a kicker + two-line headline + sub + hook refrain + tertiary italic onto one frame is the cookie-cutter over-stuff that breaks the one-big-idea law.

**THE SPLIT TRIGGER (mandatory):** if a slide carries two contrastable rhetorical beats (for example "the gap most parents miss: doing the right things the wrong way" AND "what if the problem is not effort but approach?"), it is two ideas; split it into two slides. Two contrastable beats on one frame is a split candidate, not a busy slide to compress.

| Duration | Target slide count | HARD MAX |
|----------|--------------------|----------|
| 10 min | 12 to 15 | 15 |
| 15 min | 18 to 22 | 25 |
| 30 min | 35 to 42 | 45 |
| 45 min | 50 to 58 | 60 |
| 60 min | 60 to 70 | 75 |
| 90 min | 70 to 85 | 90 |
| 120+ min | 80 to 90 | **90 absolute ceiling** |

Rules:
- The rate is roughly 1.3 to 1.5 slides per minute, tapering as duration grows. A three-hour presentation does NOT mean 300 slides. 90 is the absolute ceiling for any deck.
- Below 30 minutes, the Hormozi arc compresses: merge the origin story into 2 slides, run ONE secret instead of three, and keep the offer section proportionally intact (the pitch never gets cut).
- The agent proposes the slide count from this table; the client confirms it during the intake echo. Record `SLIDE_COUNT`.

### 4.1 Worked allocation table (apply percentages, then round and reconcile)

Percentages from the arc produce fractions. Use this pre-reconciled allocation for the common counts. For other counts, allocate proportionally, round, then add or remove slides from the Secrets sections (never from the offer section) until the total matches `SLIDE_COUNT`.

| Arc section | 45 slides | 60 slides | 75 slides |
|---|---|---|---|
| 1. Big Bold Promise | 1 | 1 | 2 |
| 2. Painful Math | 2 | 2 | 3 |
| 3. Real Problem reframe | 2 | 3 | 3 |
| 4. Commitment slide | 1 | 1 | 1 |
| 5. Origin story + authority | 3 | 5 | 6 |
| 6. Social proof | 2 | 2 | 3 |
| 7. For / NOT for | 2 | 2 | 3 |
| 8. Secret #1 (teach, proof, action) | 5 | 7 | 9 |
| 9. Secret #2 (teach, proof, action) | 5 | 7 | 9 |
| 10. Secret #3 (teach, proof, action) | 5 | 7 | 9 |
| 11. The Window / urgency logic | 1 | 2 | 2 |
| 12. Recap | 1 | 2 | 2 |
| 13. Transition to offer | 1 | 1 | 2 |
| 14. Offer + price sequence | 9 | 12 | 15 |
| 15. Guarantee + risk reversal | 1 | 2 | 2 |
| 16. Bonuses | 2 | 2 | 2 |
| 17. Final CTA + Q&A close | 2 | 2 | 2 |
| **Total** | **45** | **60** | **75** |

The offer section (rows 14 to 17) is never compressed below 10 slides on a 45+ slide deck. If `VIP_TIER` exists, it takes 1 to 2 slides inside row 14 (presented AFTER the core final price).

**MINIMUM CLOSE DENSITY (the deck must not be thin at the close):** between the Wall of Wins and the FINAL price/CTA the close carries, at minimum, objection-kill(s), the guarantee, a value recap, the post-price RE-PITCH (Section 4.2A beat after I, and Section 5.5), the scarcity beat, a last-call + join URL, and a welcome/celebration. That is NEVER fewer than ~8 slides on a 45+ deck. A deck where the Wall of Wins sits within 2 slides of the final CTA is too thin: copy QC and final-deck QC flag Wall-of-Wins-within-2-slides-of-final-CTA and the close is rebuilt to the minimum density.


### 4.2 THE PROVEN FLOW (teardown of the Lyric 75-slide deck; the narrative model)

The proven deck runs SEVEN sections with on-screen progress labels ("SECTION 3 OF 7"). Study this flow; it is the narrative the allocation table serves.

| Section | Slides (of 75) | What it does | Signature moves |
|---|---|---|---|
| 1. THE HOOK | 1 to 7 | Promise, future-pace, painful math, reframe, commitment | "30 Seats. 30 Days." promise with objection-killer sub; "This is what FULL looks like" future-pace; "$48,000 a year. Gone." empty-chairs math; "It's not your heart. It's your system." reframe; "Stay. I dare you." commitment dare |
| 2. AUTHORITY & STORY | 8 to 15 | Origin, receipts, peer proof, identity | "I didn't wake up like this"; "I'm not a coach who read about it. I built it. I run it. I'm you."; then/now split; receipts row (press, revenue, centers); "Women who look like us" representation wall; "If they did it, so can you" closer |
| 3. SECRET #1 | 16 to 24 | Belief shift on the MESSAGE | Section banner; "They're not ignoring you. Your message is wrong."; old-way/new-way split; the 4 Questions framework; verified result ("47 inquiries, one post, 7 days"); client win; 3-step action plan; vision slide; **slide 24: ANCHOR plant ("worth $5,000+. Remember this number. Keep watching.")** |
| 4. SECRET #2 | 25 to 35 | Belief shift on SPEED/system | "Fill seats in 7 days. Not 7 months."; silent-leak stat (95%); 72-Hour Rule; 5-step automated journey diagram; live-demo dashboard; sprint proof; doubter testimonial; 7-day roadmap; old/new contrast; **BUILDUP ("Imagine this running tonight") then slide 35: DROP 1 to $2,500 ("because you showed up live; this price does NOT leave this room")** |
| 5. SECRET #3 | 36 to 43 | Belief shift on ECONOMICS/LTV | "One campaign. $3K to $10K a month."; lifetime-value math ($200/wk x 52 x 3 yrs = $31,200 from ONE family); One Message/One Funnel/One Follow-up; live funnel proof; real revenue testimonial; the Window (12 to 18 months urgency logic); identity slide ("The CEO you're about to become"); recap ("You now know more than 95% of owners") |
| 6. THE OFFER | 44 to 59 | Choice frame, offer, stack, ladder | "Two Choices" frame; "Go build it" takeaway close; "Stop building. Start owning."; offer reveal with MAGIC name ("30 Kids In 30 Days Challenge"); one-promise slide; stack components one per slide, each named with a benefit and valued ($997, $1,497, $997...); VIP bonuses ($497, $997); full stack recap with checkmarks; **callback slide ("I told you to remember that number. Here it is: $5,282")**; LTV justification ("1 family = $9,600/yr; pays for itself"); **BUILDUP ("This is the part that changes everything") then slide 51: DROP 2 to $1,000 ("because you believed")** |
| 7. THE CLOSE + FINAL PUSH | 60 to 75 | Objections, drops, guarantee, proof, urgency, welcome | Objection kills ("I'm too busy" = you don't have the system; "Will it scale?"); Day 1 onboarding picture; student proof with compliance line; future-pace Day 31; **BUILDUP ("You didn't leave. That tells me everything.") then slide 65: DROP 3 to $500 on the price-tag motif**; conditional guarantee ("Fill 3 seats. Or I pay. AND I'll personally work with you until you do."); "1,000 times" receipts; Wall of Wins (6 named results); keep-guessing/build-the-system choice; final push ("This is your moment. The door is open."); last call with door-closing urgency and join URL; fast-action bonuses that expire; **slide 73: FINAL, the full strikethrough tag ($5,000 / $2,500 / $1,000 / $500 all struck) revealing GA $47 | VIP $97, 15-minute window**; full recap table with both prices; "You made it. Welcome to the family." celebration |

**Flow rules extracted (enforce in Phase 1):**
1. Every section opens with a banner/progress slide and closes with an emotional punctuation slide.
2. Each Secret follows: claim -> problem/stat -> framework -> proof -> action plan -> vision.
3. Proof appears within 2 slides of every claim. Named, located testimonials ("Janelle, Atlanta GA") with compliance disclaimers.
4. The ladder spreads across sections (rungs near the 32/47/68/87/97% marks), every drop earns its reason, every drop follows a BUILDUP.
5. Open loops plant early and close on screen with explicit callbacks.
6. The deck talks TO one person in the client's voice, in second person, with the client's edge (the proven deck: edgy, unapologetic, emotionally poignant). TONE from intake governs every line.


### 4.2A THE BLACKCEO SIGNATURE WEBINAR ARC (the canonical slide-by-slide journey)

The proven flow table (4.2) is the narrative MODEL, the doctrine (4.3) is the rule SET, and Section 4.4 lists the ten REQUIRED components. This section fuses them into ONE named, canonical arc: the slide-by-slide journey in the operator's own revealed order, where every named section maps to (a) the components that belong in it, (b) the typography and standalone-art standard applied to its slides, and (c) the QC gate that verifies it. A great presentation is a JOURNEY that creates a Significant Emotional Experience, not a deck of facts; this arc is that journey made reproducible.

**The order is the order the operator reveals things live:** open on the hook, care about the audience and let them see themselves, make the promise, tell the story, teach one big idea per slide (each slide carrying the ONE big idea and, where it earns it, a light pitch; the hook refrains on a scheduled CADENCE, not every slide), prove it with who-says-so plus the wall of wins, make the offer on a gradual spread ladder that ADDS value at every drop, guarantee it, close on real scarcity, and call the hook back one last time. The ten named arc sections (A through J) are the human-readable journey; the seven proven sections in 4.2 are how the slide-count math allocates it; the ten required components in 4.4 are the elements each section delivers.

**Every slide must satisfy three layers at once:** (1) typographically correct to the Montserrat weight-mapped law, (2) a standalone piece of art that reads alone, and (3) carrying its beat in the journey (its one big idea, and WHERE SCHEDULED a hook refrain or a ladder rung). A slide failing any one of the three is not done.

| Arc section | The beat | Components (from the doctrine 4.3 + the ten required 4.4) | Typography + art | Proven section (4.2) | Primary QC gate |
|---|---|---|---|---|---|
| **A. HOOK OPEN** | Open ON the hook as a big specific promise; sing the first verse immediately. | Hook as a singable line (rule 1, component 2); big bold promise; objection-killer sub; first hook occurrence inside the first 10 to 15%. | A4 Type-Dominant Punch; two-line Montserrat Black headline (charcoal, never pure black); gold kicker + rule; logo chip. | THE HOOK (1-7) | Copy QC c1/AF-C2 (first occurrence early), AF-C5 (<= 9 words), AF-P10/I9 (designed type), AF-P11/I10 (standalone art), AF-C1 (no em dash). |
| **B. CARE / SEE-YOURSELF** | Before credentials, show you care about THEM; let them see themselves and FEEL the pain. | Care-before-credentials; see-yourself story; pain gets its OWN slide (rule 9) with an emotionally driven, recognizable image; future-pace; painful math; reframe; commitment. | A1 Full-Bleed Photo + scrim for pain beats; A3 Photo-top/Data-bottom + giant number for the math; emotionally driven recognizable photography. | THE HOOK (pain/future-pace) | SP-CARE + SP-JOURNEY/SP-SEE (final-deck structural completeness); Image QC i11 (face matches pain), i12 (real-world setting); AF-P7 (hair+clothing+expression). |
| **C. THE PROMISE** | State the promise plainly; plant promises the offer will fulfill. Selling starts HERE, at the front. | Promises pitched not products (rule 2, component 1); running promise inventory; first light pitch woven in (rule 7); no back-loaded selling. | A4 punch or A1 future-pacing; the promise (and its number) rendered as designed type. | THE HOOK -> AUTHORITY | Copy QC c15 / c18 (promise leads); SP-light-pitch / GP-11 (distributed, not back-loaded); a hook refrain candidate in this section. |
| **D. STORY** | Origin and authority through demonstrated EXPERTISE, not charisma, AFTER caring about the audience. | Origin story; the Story Arc short-term-fix vs long-term-identity (component 8); then/now split; receipts row; representation wall; expertise-over-charisma; entry-product-as-buy-in. | A2 Photo-one-side+Text for origin/authority; A5 Portrait for the "I'm you" slide; cast to the captured REPRESENTATION_MIX exactly. | AUTHORITY & STORY (8-15) | Quote slides carry the NAME ONLY (T.D. Jakes rule); AF-R1/AF-R2 representation tally (bidirectional); SP-OLDNEW (old-to-new bridge); story-arc structural check (component 8). |
| **E. TEACHING** | Teach the belief shifts as an APPETIZER not dinner; one big idea per slide; each methodology piece is a light sales point; the hook refrains after a proof BEAT (a scheduled reprise), not on every proof slide. | One big idea per slide (rule 4, component 5); PSD (Point-Story-Demo); old-to-new bridge; intrigue slides (rule 10); compare/contrast (rule 11); triple alliteration (rule 13); light pitch on each teaching slide (rule 7); appetizer not dinner (rule 8); teach-themselves. | A2 teach-with-person; A3 stats/before-after; A1 vision; each idea its own emotionally precise image; giant number is the hero where a number is the idea. | SECRETS 1-3 (16-43) | Copy QC AF-C6 (multi-idea = auto-fail), c15 (not over-taught, intrigue, compare/contrast, light pitch), SP-PSD, SP-TEACH, c16 (text-anchor variation); hook refrains after proof. |
| **F. PROOF: WHO SAYS SO + WALL OF WINS** | Answer "who agrees with you besides you?" | Case studies / who-says-so (rule 12, component 3); named/located testimonials with compliance lines; white-paper studies; the Wall of Wins (component 4); proof within 2 slides of every claim. | A3 metrics + verified-result pills; A2 testimonial portraits; A4 wall-of-wins grid; compliance line on every results claim. | within each Secret + close | Zero-proof deck fails (component 3); AF-C3 (no fabricated proof); Wall of Wins presence (component 4); hook refrains right after the proof. |
| **G. THE OFFER (gradual spread ladder)** | Make the offer and walk the price DOWN gradually across the deck, adding value at every drop, proof between drops, until the real price shatters the ladder. | True-value ANCHOR planted gradually (a value plant, NOT a drop) with the memory hook; Hormozi value stack; case studies BETWEEN drops; a BUILDUP before EVERY drop; each drop earned; each drop ADDS value (the red rule); the anchor callback; cost-versus-value (LTV math OR the priceless pitch); FINAL real price far below the ladder; the Gradual Price Ladder (component 9); VIP side-by-side; roadmap the program; serve emotion AND logic. | A4 Type-Dominant Punch for anchor/drops/FINAL; the price-tag motif; superseded prices struck with a DRAWN double-thickness gold diagonal (the anchor is NOT struck); giant numbers 110-150pt. | THE OFFER (44-59) + drops in close | AF-C7 (the gradual-drop choreography gate: spread not stacked, every drop earned + built up + ADDS value, FINAL below the ladder), AF-C4 (cross-slide numeric consistency), c17 (anchor callback), SP cost-vs-value + emotion-and-logic, Offer Price Strategist Gate 10. |
| **H. GUARANTEE** | Reverse the risk so the logical justifier can say yes. | The Guarantee (component 6) in one bold sentence + conditional logic in the sub; the operator-preferred SERVICE GUARANTEE ("your next 30 days is on us"); positioned after the final price. | A4 punch or A5 (founder + certificate); one bold designed sentence. | THE CLOSE (guarantee) | Offer Price Strategist SOP 9.8 (guarantee owned + gated); guarantee structural check (component 6); designed type + standalone art. |
| **I. SCARCITY / CLOSE** | Close on REAL scarcity and urgency; total the value; drive the action. | The Scarcity Factor (component 7); objection-kill slides; two-choices frame; full stack recap (checkmarks + both prices); fast-action bonuses that expire; last-call urgency + join URL; ALWAYS pitch something (rule 14); real quantity scarcity + real time urgency. | A4 recap table + final push; A1 emotional last-call; the recap repeats every number identically. | THE CLOSE + FINAL PUSH (60-75) | Scarcity-factor presence gated (component 7); scarcity/urgency TRUE (no fabrication); c15 (a paid pitch exists); AF-C4 (numeric consistency); composed-slide asserts AF-F1..F4. |
| **I.5 RE-PITCH (after the FINAL price, before the hook callback)** | After the real price is revealed, do NOT just end. Recap everything, reset the offer, and re-arm urgency across 4 to 7 slides. | The RE-PITCH movement (Section 5.5 post-price sequence + Offer and Price Strategist SOP 9.9): full "here is everything you get" recap table (each component + its $ value + checkmarks), total value restated against the FINAL price (the value gap), the promise inventory re-listed, the guarantee restated, the top 2 to 3 objection kills, the scarcity/urgency window re-armed (real spots/time only), final CTA + join URL. | A4 recap table; the recap repeats every number identically; price-tag motif for the value gap. | THE CLOSE + FINAL PUSH (post-price) | New copy QC criterion 23 (re-pitch present: a 4 to 7 slide recap+value+promise+reset block exists after the final price); AF-C4 (numeric consistency); minimum close density (Section 4.1). |
| **J. HOOK CALLBACK** | Reprise the hook as the final substantive beat; welcome them in. | Hook reprise as the FINAL substantive slide; welcome/celebration; open Q&A; the hook graduates into the signature quote/hashtag. | A4 Type-Dominant Punch carrying the hook one last time, designed and standalone. | THE CLOSE (reprise + welcome) | Hook reprised on the final slide (hard requirement); AF-C2 (total count approaching ~10x, floor 7). |

**THE CONNECTIVE TISSUE (the deck-WIDE rules that run BETWEEN the sections; this is what makes it a continuous song, not ten disconnected sections):**

1. **Hook cadence is a SCHEDULED refrain, not wallpaper on every slide.** The hook stands on its OWN dedicated slide 3 to 4 times across a ~30-min deck (open verse, one mid reprise, one post-proof reprise, close reprise); light refrains only where a proof or a beat earns it. Floor 7 total occurrences on a long deck (the mechanical auto-fail AF-C2), first occurrence inside the first 15%, a refrain candidate in every section, never more than 2 consecutive ladder/close slides without the hook nearby. HARD CEILING: roughly 1 occurrence per 6 slides, and NEVER two consecutive slides carrying the hook. The hook is a refrain, not a footer stamped on every frame.
2. **Proof is woven BETWEEN the drops, not bunched.** Each drop is followed within 2 slides by who-says-so proof; the hook refrains right after that proof; proof earns the next rung.
3. **Value is ADDED at every drop, never subtracted.** "The lower the price, the greater the value." A drop that strips value to justify the discount is a doctrine violation (AF-C7).
4. **The light pitch is woven from the first verse.** Every named methodology piece is a soft sales point; selling is distributed across the teaching, never back-loaded.
5. **A slide earns the next slide.** Each teaching slide opens a small loop or asks a question (intrigue); the next slide pays it or contrasts it (compare/contrast). Open loops planted early close on screen with explicit callbacks (the anchor callback is the canonical example).
6. **Transitions: every section opens with a banner/progress slide and closes with an emotional punctuation slide.** Section progress labels orient the audience; the punctuation slide lands the feeling before the next section begins.
7. **Move the words around the frame so eyes never fade out.** Vary the text anchor (bottom band / left block / right block / center); never more than 2 consecutive slides in the same position.
8. **The slide is not the script.** The slide carries the one big idea; the presenter carries the narration in the PRESENTER NOTE.
9. **Emotional sequencing.** The journey moves through a designed emotional sequence (care first, see-yourself, felt pain, a promise, a story they belong in, teaching they arrive at themselves via PSD and old-to-new bridges, proof, an offer that serves both heart and head, a sticky reprise). This is what turns information into a Significant Emotional Experience.
10. **No em dashes, anywhere, ever.** Auto-fail on sight (AF-C1 / AF-I7).
11. **Echo before you build; the checklist is a list of promises (component 10).** The agent echoes the mission, produces a PRD + checklist, waits for go, and self-verifies against the checklist before declaring done. Never die silently.
12. **Enhance, don't replace.** From a client's existing deck: ADD slides and improve the design, but never change the client's intent, words, or methodology.

The Director walks this arc at Section 9.4 of director-of-presentations.md (slide-count math and arc allocation) and hands it to the Slide Copywriter and the Offer and Price Strategist. The QC Specialist verifies it at the copy gate (Phase 1Q) and re-verifies the structural completeness on the assembled deck (Phase 6). The full elevated reference (each section's grounding quoted to the transcript line, plus the grounded-vs-elevated ledger) is the ENHANCED PRESENTATION MASTERY study from which this section was distilled.

---

### 4.3 THE BLACKCEO PITCH DOCTRINE (the operator's intelligence; every writer and QC agent internalizes this before Phase 1)

These are the principles the operator teaches live. They are not optional style notes; they are the logic the deck is built on, and copy QC scores against them.

**1. THE HOOK DOCTRINE (the Purple Rain rule).** A presentation is written like a song: there is a rhythm, and there is a hook. A 5-minute song sings its hook 10 times so you remember a 5-minute song; most presenters give a 30-minute presentation and say their hook once. This system writes the hook and SINGS it.
- The hook is the strongest part of the promise, the one thing the audience wants most, compressed into one singable line (proven deck: "30 Kids. 30 Days."; another client: "There is a difference between parenting by control and parenting through clarity.").
- Phase 1 derives the hook from `BIG_PROMISE` + `OFFER_STACK`, records it as `HOOK` in intake.json, and the owner confirms it at the approval gate.
- **The hook appears AT LEAST 7 TIMES across a long deck** as a SCHEDULED refrain (roughly one occurrence per 8 to 10 slides, never fewer than 7 on a 45+ deck; a short ~30-min deck carries fewer total, anchored on the 3 to 4 dedicated hook slides plus the proof-earned refrains). Each occurrence is tied back to the content on that slide; it is a refrain on a cadence, not wallpaper on every slide. HARD CEILING: never on two consecutive slides, roughly no more than 1 occurrence per 6 slides.
- The hook gets DEDICATED slides of its own (A4 type-dominant treatment). **Scale rule:** on a ~30-min deck the hook stands on its OWN dedicated A4 type-dominant slide 3 to 4 times (open verse, one mid reprise, one post-proof reprise, close reprise), and no more; pair this with the consecutive-slide ceiling (never two consecutive slides carrying the hook, roughly 1 occurrence per 6 slides). Everywhere else there is no hook footer. Scale up the dedicated count modestly on longer decks; the open and the close reprise are always two of them.
- **Sing it early.** Nobody waits until the end of the song to sing Purple Rain. First occurrence lands inside the first 10 to 15% of the deck, then recurs through every section on its scheduled cadence, and reprises in the close.
- **Refrain after proof.** When a story or case study proves the point, the hook is run again at the bottom of that slide, because the proof just earned it.
- A strong hook can graduate into the client's signature quote and hashtag. Quote slides carry the client's NAME ONLY, no credentials (the T.D. Jakes rule: we quote the name, not the resume).

**2. PEOPLE BUY PROMISES, NOT PRODUCTS.** They do not buy the product; the product is just a reflection of the promise they want. Every teach and offer slide pitches the PROMISE. If the promise is strong enough, the product sells itself. Phase 1 maintains a running promise inventory: what is this product promising, slide by slide?

**3. THE LOWER THE PRICE, THE GREATER THE VALUE.** Every price drop ADDS something to the table; it never takes anything off. Drop to $1,000 AND stack the Blueprint AND the automation bonus on top. Most people discount by stripping; this system discounts by stacking. Copy QC verifies that every DROP slide or its immediate successor adds new named value.

**4. THE GRADUAL VALUE REVEAL, NOT THE CLICHE.** Never the worn-out "this is worth $25,000 but today only $2." The anchor arrives as an honest question planted mid-teach: "What is a system like this actually worth?" Then the ladder walks down gradually, each rung earned (showed up live, believed, stayed). The audience keeps leaning in because every stretch of staying lowered their price: "wait, I just hung around and got myself to $2,500; what else am I going to get?"

**5. EMOTION BUYS. LOGIC JUSTIFIES.** People buy on emotion and justify with logic, and in couples the two roles usually split: one partner is emotionally ready, the other needs the logical case. The deck must serve BOTH in every offer section: emotionally driven imagery and future-pacing for the heart, and explicit math (LTV, cost of inaction, payback) for the justifier. A deck that only inspires loses the justifier; a deck that only calculates loses the buyer.

**6. COST VERSUS VALUE.** Every pitch explicitly answers two questions: what is the COST of not taking action, and what is the VALUE of taking action? If the offer produces money, do the math on screen (1 family = $9,600/yr; 3 = $28,800). If the offer does not produce money, run the PRICELESS PITCH (the American Express frame): hot dog $5, parking $20, the outcome they actually want: priceless. Never fabricate dollar values for non-monetary outcomes; elevate them above money instead.

**7. LIGHT PITCHES, WOVEN.** Do not save the pitch for the end. Softly sing the song of the program throughout: "when you work with us," "inside our program," "when you attend this workshop." Every named piece of the client's methodology (their identity development structure, their guided development system, their frameworks) is a named SYSTEM, and every named system is a light sales point planted inside the teaching.

**8. APPETIZER, NOT DINNER.** Teach enough to prove competence and shift beliefs; never so much that they are full. If you over-teach, they have no reason to buy dinner. Each Secret teaches the WHAT and the WHY and one quick win; the complete HOW lives inside the offer.

**9. PAIN GETS ITS OWN SLIDE.** Each distinct pain point is ONE slide with ONE emotionally driven image; never a bulleted list of four pains on one slide. They have to feel the weight of each one, and a picture is worth a thousand words: the image must make the viewer say "that is exactly how I feel." (Four pain points = four slides, no matter what.)

**10. INTRIGUE SLIDES.** A slide that makes the audience ask a question is a strong slide ("doing the right things, but in the wrong way?" makes you ask: what do you mean, the wrong way?). Plant at least one genuine curiosity gap per section.

**11. COMPARE AND CONTRAST, CONSTANTLY.** Old way vs new way. Control vs clarity. Keep guessing vs build the system. Two-sided slides that show how each path SHOWS UP in real life are the workhorses of belief shift; use them in every Secret and again in the close.

**12. WHO SAYS SO OTHER THAN YOU (case studies / third-party proof, REQUIRED).** Case studies are not decoration; they are the answer to "who agrees with you besides you?" Third-party proof, studies, and white papers are woven BETWEEN the price drops, not clustered. Proof within two slides of every claim, plus white-paper or research backing where the niche expects it. Named, located testimonials. **A deck with ZERO third-party proof FAILS:** the Deep Research Specialist surfaces the GP-8 zero-proof alert, the Slide Copywriter must place at least one external-corroboration ("who says so") beat woven between the drops, and copy QC scores its presence (a deck where every proof point is the client's own assertion with no case study, study, or white paper is a fail, not a flag).

**13. TRIPLE ALLITERATION.** Lists of three should alliterate when natural ("confident, consistent, and clear"), and the trio can become formulaic: Confidence + Consistency + Clarity = Effective Guide. When a value trio is part of the pitch, each value word can earn its OWN slide, because each one is being sold.

**14. ALWAYS PITCH SOMETHING.** Even a "free strategy session" webinar pitches a paid something, even if it is $47 or $97. If they are showing up, the event produces revenue and commitment. Free-only closes are not allowed without explicit owner sign-off.

**15. THE SLIDE IS NOT THE SCRIPT.** Never put the words the presenter is going to SAY on the slide. The slide carries the one big idea; the presenter carries the narration; that separation is WHY the audience listens instead of reading ahead. The spoken words live in the PRESENTER NOTE.

**FORBIDDEN ON ANY AUDIENCE-FACING SLIDE (auto-fail on sight, same severity tier as the em-dash ban):**
1. **Presenter narration / what-to-say lines** ("today I'm gonna show you why...", "let me explain...", "in the next ten minutes I'll...").
2. **The AI's own meta-commentary or reasoning** (any note the model wrote to itself; any "here we will...", "this slide should...").
3. **IMAGE / SCENE DESCRIPTIONS as visible copy** (the art direction leaking onto the slide as headline or sub: "same parent, same child, two completely different rooms", "the senior engineer who hit every goal and still feels lost"). The scene is RENDERED, never written as copy.
4. **TELEGRAPHING / stage-direction** ("one last proof before you decide", "this is not just a webinar", "before you decide", "hold on, the value is still climbing", "the lower the price, the greater the value"). The mechanic stays in the PRESENTER NOTE; it never narrates itself on the slide.
5. **The literal word "webinar"** on any audience-facing slide. The deck IMPROVES on the gold standard here rather than transcribing it: even where a reference deck says "webinar", this SOP bans it on-slide.

These are on-slide copy bans. Each lives in the PRESENTER NOTE instead. A slide whose baked copy contains any of the five fails copy QC and is sent back for rewrite/re-render.

**16. EYES MUST MOVE.** Vary the text placement across consecutive slides (bottom band, left block, right block, center punch). Putting the words in the same place every time causes the audience to fade out. The archetype rotation exists to keep their eyes hunting; copy QC flags more than 2 consecutive slides with the same text anchor position.

**17. PREMIUM MEANS PHOTOGRAPHY, NOT EMOJIS.** Icons and emojis cheapen a premium deck. Emotion is carried by photographic imagery and typography, never clipart glyphs.

**18. ROADMAP THE PROGRAM.** When the offer is a challenge or program, lay out the journey on slides: Day 1, Day 2, Day 3; Week 1 through 6; the 90-day plan. Future-pacing the program itself builds excitement and gives the logical justifier their structure.

**19. THE STORY ARC (short-term fix vs long-term identity; self-recognition).** Every deck carries a narrative arc that contrasts the SHORT-TERM FIX the audience is currently chasing against the LONG-TERM IDENTITY transformation the offer actually delivers, and walks them to SELF-RECOGNITION ("that is exactly me"). The fix is the band-aid they keep buying (control, behavior management, the quick patch); the identity is who they become (clarity, ownership, the CEO they are about to be). The arc names the short-term fix, shows why it never holds, then reframes the real outcome as a durable identity change, so the audience recognizes themselves in both the before and the after. At least one explicit short-term-fix-vs-long-term-identity contrast beat is required, and the arc is what makes the audience say "that is me" rather than "that is interesting."

**20. THE WALL OF WINS (wall of results, REQUIRED).** The deck carries a Wall of Wins (also called the wall of results): a dedicated results/testimonial wall element that stacks multiple named, located client wins in one view (the proven deck: six named results). It is distinct from the single proof-within-two-slides testimonials; it is a deliberate concentration of social proof near the close that says "look how many people this already worked for." A deck with no wall of wins is missing a required element. As the client accumulates wins, the wall grows.

**21. THE GUARANTEE (required), THE SCARCITY FACTOR (required), and THE CHECKLIST IS A LIST OF PROMISES.**
- **THE GUARANTEE:** every deck states an explicit guarantee / promise / risk-reversal (one of the four guarantee types in Section 5.4; the operator-preferred frame for service businesses is the SERVICE GUARANTEE, "if you do not get the result, your next 30 days is on us"). A deck with no guarantee beat is incomplete.
- **THE SCARCITY FACTOR:** the close carries a real scarcity / last-calls / doors-closing element (real spots or real time only, never fabricated; fake scarcity is a blocking flag). A close with no scarcity beat is incomplete.
- **THE CHECKLIST IS A LIST OF PROMISES:** "a checklist for an AI is a list of promises." Before any agent says "I'm done," it walks its OWN checklist and verifies every promise was kept. The agent echoes the mission, builds its own checklist of promises (this very SOP's required components among them), and checks it before delivery (Section 3.3). This is the QC philosophy that the other nine components are scored against: each required component is one promise on the checklist, and the checklist is not satisfied until every promise is verified present.

---

## 4.4 THE TEN REQUIRED PRESENTATION COMPONENTS (named, mandatory, each QC-gated)

These are the ten presentation components the operator named as REQUIRED. Each is a mandatory element of every deck and each has an explicit QC gate. This table is the master index; the doctrine above (Section 4.3) defines each one, the role SOPs produce them, and the QC Specialist (Section 6, Section 11.3) gates them.

| # | Component | Where it is produced | QC gate |
|---|---|---|---|
| 1 | **THE PROMISE** (pitch the promise, not the product; lead with the core promise) | Copywriter leads every teach/offer slide with the promise (4.3 rule 2); Director records `BIG_PROMISE` in the PRD | Copy QC criterion 12 doctrine battery (promises pitched, not products) |
| 2 | **THE HOOK** (written like a song, derived from the strongest promise, sung approximately 10x, minimum 7) | Hook Strategist derives + maps it; Copywriter places it; Presenter Coach sings it in the talk track | Copy QC criterion 11 mechanical HOOK COUNT (auto-fail under 7) |
| 3 | **CASE STUDIES / "WHO SAYS SO OTHER THAN YOU"** (third-party proof, studies, white papers woven between the drops; zero-proof deck FAILS) | Deep Research Specialist feeds external corroboration; Copywriter places it between drops | Copy QC + final-deck structural-completeness (zero external proof = fail, not flag) |
| 4 | **WALL OF WINS / WALL OF RESULTS** (a concentrated results/testimonial wall element) | Deep Research + client `PROOF_ASSETS` feed it; Copywriter builds the wall slide near the close | Copy QC + final-deck structural-completeness (wall present) |
| 5 | **ONE BIG IDEA PER SLIDE** (one idea, large; multi-idea slide FAILS) | Copywriter (Section 5.1 limits); slide math (Section 4) | Copy QC AUTO-FAIL on any multi-idea slide |
| 6 | **THE GUARANTEE** (explicit promise / guarantee / risk-reversal) | Offer Price Strategist sets the guarantee type; Copywriter writes the guarantee slide | Copy QC + final-deck structural-completeness (guarantee present) |
| 7 | **THE SCARCITY FACTOR** (last-calls / doors-closing in the close; real only) | Offer Price Strategist + Copywriter write the close | Copy QC + final-deck structural-completeness (real scarcity present); fake scarcity = blocking flag |
| 8 | **THE STORY ARC** (short-term fix vs long-term identity; self-recognition) | Copywriter writes the arc; Director's arc allocation carries the contrast beat | Copy QC + final-deck structural-completeness (short-term-fix vs long-term-identity contrast present) |
| 9 | **THE GRADUAL PRICE LADDER** (value-plant anchor -> spread earned-reason drops -> ADD VALUE every drop -> final late) | Offer Price Strategist owns the spread ladder; Copywriter writes the rungs | Copy QC ladder integrity (criterion 17) + Offer Price Strategist gates |
| 10 | **"A CHECKLIST FOR AN AI IS A LIST OF PROMISES"** (the QC / checklist philosophy) | Director echo gate (Section 3.3): the agent builds its own checklist of promises and checks it before "done" | Director echo gate + every QC gate is the enforcement of the checklist |

---

## 5. PHASE 1: WRITE THE SLIDES (THE WORDS, BEFORE ANY PICTURES)

**Model: Kimi 2.6 per Section 1.** Output: `working/copy/slides_copy.md`. Every slide gets its own entry. The presentation IS this file; the images only dress it.

### 5.1 Hard copy limits (enforced by copy QC, non-negotiable)

These limits exist because gpt-image-2 garbles dense text and because one big idea per slide is the law of this SOP.

- **Headline: 9 words maximum.** Target 4 to 7.
- **Sub-copy: 18 words maximum.** One line. Optional.
- **Maximum 3 text blocks per slide** (headline + sub-copy + one supporting element such as a stat, label, or CTA chip).
- **TOTAL words per slide ceiling: 30 words** across ALL on-slide text elements combined (headline + sub + supporting + any kicker/chip, EXCLUDING the PRESENTER NOTE which is never on the slide). A slide can pass the 3-block test and still be over-stuffed; this mechanical ceiling is a copy-QC auto-fail. If a slide is over 30 on-slide words, it carries more than one idea: split it. Bullet and value-stack slides are governed by their own line caps below, not this single-idea ceiling.
- **Bullet slides: maximum 5 bullets, 7 words per bullet.** Bullets only when the idea is genuinely a list (stack components, "this is for you if", recap). Never bullets as a substitute for choosing the one big idea.
- **Value stack slides: maximum 6 line items, each `Name + $X value`, 7 words per name.** If the stack has more than 6 components, split across two slides.
- **Numbers are heroes.** When a number is the idea ($24,997, 38x, 90 days), the number IS the headline and everything else shrinks around it.
- If a slide's copy cannot fit these limits, the slide has more than one idea. Split it.
- **THE HOOK (mandatory):** derive `HOOK` per Section 4.3 rule 1 before writing slide 1. Sing it at least 7 times: first occurrence inside the first 10 to 15% of the deck, one dedicated A4 hook slide, refrains at the bottom of proof slides, light occurrences through every section, reprise in the close. Tag every occurrence in the slide entry (`HOOK_REFRAIN: yes`).
- **THE SLIDE IS NOT THE SCRIPT:** slide text never duplicates the presenter's narration. If the headline says what the PRESENTER NOTE says, rewrite one of them.
- **PAIN POINTS:** one pain per slide, one emotionally driven image per pain, never a bulleted pain list.
- **TEXT ANCHOR VARIATION:** record each slide's text anchor position (bottom band / left block / right block / center). Never more than 2 consecutive slides with the same anchor.
- **IMAGE POSITION VARIATION:** record each slide's image zone (left / right / top / bottom / full-bleed / none). Never more than 2 consecutive slides with the same image position. This mirrors the text-anchor rule so the deck rotates layouts and never stamps one frame (a deck that is photo-right / type-left on every slide fails layout-variety QC).
- **TYPE-DRIVEN HOOK SLIDE:** every dedicated hook slide (archetype A4) is typography-driven: NO image, OR a background image at <= 15% opacity with large designed type over it. The hook stands as type, not as a photo with a caption.

### 5.2 Per-slide entry template (every slide in slides_copy.md uses this exact format)

```
## SLIDE NN
SECTION: [arc section name]
PURPOSE: [the one big idea, one sentence]
ARCHETYPE: [A1-A5 from Section 7.2]
LADDER: [none | ANCHOR | BUILDUP | DROP1 | DROP2 | DROP3 | FINAL]
HEADLINE: "[exact words, <= 9 words]"
EMPHASIS: "[which word(s) get accent color]"
SUB-COPY: "[exact words, <= 18 words, or NONE]"
SUPPORTING: "[third text block if any, or NONE]"
PROOF/ASSET: [client asset used, or [CLIENT TO SUPPLY], or NONE]
PEOPLE: [yes/no; if yes, which REPRESENTATION_MIX group this slide draws from]
HOOK_REFRAIN: [yes/no; if yes, where the hook line sits on the slide]
TEXT_ANCHOR: [bottom band | left block | right block | center punch]
PRESENTER NOTE: [2 to 4 sentences of what the presenter SAYS on this slide]
```

The PRESENTER NOTE field is mandatory. It becomes the speaker notes in the final PPTX (Phase 6). A deck without a script is half a deliverable.

### 5.3 Gold-standard examples (calibrate to these)

**Example A: Big Bold Promise slide (typography archetype)**
```
## SLIDE 01
SECTION: Big Bold Promise
PURPOSE: Plant the one outcome this webinar delivers, with the objection pre-killed.
ARCHETYPE: A4 Type-Dominant Punch
LADDER: none
HEADLINE: "Fill Your Program In 30 Days"
EMPHASIS: "30 Days"
SUB-COPY: "Even if nobody knows your name yet."
SUPPORTING: NONE
PROOF/ASSET: NONE
PEOPLE: no
PRESENTER NOTE: Welcome them in, then make the promise plainly. Name the elephant: most of you think you need a bigger audience first. You do not, and in the next [X] minutes I will prove it. Set the frame that staying to the end pays.
```

**Example B: Price anchor slide (offer archetype)**
```
## SLIDE 48
SECTION: Offer + price sequence
PURPOSE: Land the total value anchor as one undeniable number.
ARCHETYPE: A4 Type-Dominant Punch
LADDER: BUILDUP precedes; this slide closes the stack before DROP2
HEADLINE: "Total Value: $24,997"
EMPHASIS: "$24,997"
SUB-COPY: NONE
SUPPORTING: "Everything you just saw. All of it."
PROOF/ASSET: NONE
PEOPLE: no
PRESENTER NOTE: Pause here. Recap the stack components by name only, fast. Let the number sit on screen in silence for two full beats before the next sentence: and you are not going to pay anything close to that.
```

### 5.4 The Hormozi pitch engine (embedded frameworks, apply throughout)

These are the mechanics from $100M Offers that make the pitch work. The writer agent applies them; copy QC checks for them.

**The Value Equation (the lens for every teach and offer slide).** Value = (Dream Outcome x Perceived Likelihood of Achievement) / (Time Delay x Effort and Sacrifice). Increase the top two, drive the bottom two toward zero. The three Secrets should each collapse one of these variables: typically Secret 1 reframes the Dream Outcome and likelihood, Secret 2 kills Time Delay (speed, the system), Secret 3 kills Effort and Sacrifice (done-for-you, economics). Offer slides must speak to all four.

**Offer stack rules (from the Bonuses chapter).** A single offer is less valuable than the same offer broken into named component parts and stacked. Every stack component and bonus gets: (a) a special name with a benefit in the title, (b) one line on how it relates to their problem, (c) a standalone dollar value. Never discount the core offer to close; ADD bonuses instead. Bonuses are revealed AFTER the final price in a straight-price pitch, and woven through the drop in a gradual pitch.

**Naming (MAGIC formula) for the offer and bonuses.** Magnet (a reason why), Avatar (who it's for), Goal (the dream outcome), Interval (time frame, where compliant), Container (Challenge, Blueprint, Accelerator, Intensive, System...). Rhyme or alliteration when natural, never forced.

**Guarantees (pick one with the client, from the four types).** Unconditional (any reason refund), Conditional (do-the-work clause, allows bolder promises), Anti-guarantee (all sales final, framed as exclusivity), Implied (performance-based). For service businesses wary of refunds, the operator-preferred frame is the SERVICE GUARANTEE: "if you do not get the result, your next 30 days is on us" or "five more sessions until your breakthrough." It reverses risk without writing checks. The guarantee slide states the guarantee in one bold sentence with the conditional logic in the sub-copy.

**Scarcity and urgency (the Window section).** Scarcity is quantity (limited spots, real numbers only). Urgency is time (cohort start date, price expiration, market timing). Use logical, true urgency. Fabricated scarcity is forbidden and copy QC fails it.

### 5.5 The price sequence (both modes, fully specified)

**Mode `drop` (the proven Lyric SPREAD LADDER, the default and strongly recommended):**

The single most important discovery from the proven run: **the drops are SPREAD ACROSS THE DECK, not stacked at the end.** Each drop is planted inside the content, each is preceded by an emotional BUILDUP slide, and the audience rides the ladder down for the entire webinar. On the 75-slide deck the ladder was: ANCHOR at slide 24, DROP 1 at 35, DROP 2 at 51, DROP 3 at 65, FINAL at 73 (roughly the 32%, 47%, 68%, 87%, and 97% marks; place ladder rungs at those proportional positions on any slide count).

Every ladder slide carries a LADDER tag in slides_copy.md: `ANCHOR`, `BUILDUP`, `DROP1`, `DROP2`, `DROP3`, or `FINAL`.

1. **ANCHOR (plant it mid-teach, inside Secret #1 or #2):** a "value reality check" slide that establishes what the system is WORTH (e.g., "a system like this is worth $5,000+") with an explicit memory hook in the copy and presenter note: "Remember this number. Hold onto it. Keep watching." This is a VALUE anchor, not a price.
2. **BUILDUP before every drop (mandatory):** each drop is immediately preceded by one emotional buildup slide (A1 archetype, future-pacing or recognition: "Imagine this running tonight," "You didn't leave. That tells me everything."). A drop with no buildup is a discount; a drop with a buildup is a reward.
3. **DROPS, each with a stated earned REASON:** Drop 1 mid-content ("because you showed up live"), Drop 2 in the offer section ("because you believed"), Drop 3 in the close ("because you stayed"). Each drop slide shows the prior price(s) struck through (drawn gold lines per Section 7.4) above the new price, ideally on the price tag motif. Drops are strictly decreasing.
3a. **VALUE STACK as component cards, spread across the offer section (the slow-drop enforcement):** every offer component gets its OWN slide with its OWN $ value chip, on a consistent component-card template (the $ chip in the same placement on every card). Spread these cards across the offer section rather than dumping them; then a TALLY slide sums them to the anchor (the Lyric model: $997 + $1,497 + $997 + $497 + $297 + $997 = $5,282 across the stack slides, callback-proved). Add a PROMISE slide between drops: between DROP1 and DROP2, and between DROP2 and FINAL, restate the promise just earned (the running promise inventory, doctrine rule 2), so each drop is earned by a promise just made. Add a VALUE-GAP slide immediately before FINAL that quantifies the gap (total value, e.g. $5,282, vs the price today) before the real price is revealed. Each drop or its immediate successor ADDS a named $-valued component; no drop strips value to justify the discount.
4. **CALLBACKS:** when the full stack total is revealed in the offer section, the copy explicitly calls back to the anchor: "I told you to remember that number. Here it is." Open loops planted early get closed on screen.
5. **FINAL (the real price, far below the ladder):** the actual buy price lands at the LAST rung and is dramatically below the value ladder (proven deck: $5,000 value ladder walked to $500, then the real price revealed at GA $47 / VIP $97 with a 15-minute action window). The ladder walks VALUE down; the price reveal then shatters even the lowest rung. The final slide shows the entire strikethrough stack on one tag.
6. **VIP (if `VIP_TIER`):** presented WITH the final price as a two-option close (GA price | VIP price side by side), not after it.
7. **Post-price sequence (includes the mandatory RE-PITCH movement):** after the FINAL price the deck does NOT just end. It runs the RE-PITCH: a 4 to 7 slide block AFTER the final price (owned by Offer and Price Strategist SOP 9.9) that (1) shows a full "here is everything you get" recap table with each component + its $ value + checkmarks, (2) restates total value against the FINAL price (the value gap), (3) re-lists the promise inventory, (4) restates the guarantee, (5) kills the top 2 to 3 objections, (6) re-arms urgency/scarcity (the action window re-armed, real spots/time only), (7) delivers the final CTA + join URL. Then the two-choices frame, fast-action bonuses with expiry, last-call urgency with the join URL on screen, and the welcome/celebration slide, before the hook reprise (arc J) closes. A deck whose price is revealed and then simply ends is INCOMPLETE.

**Mode `straight`:**
1. VALUE STACK (same rules), 2. ANCHOR with memory hook, 3. ONE price reveal slide ("all of that, for `FINAL_PRICE`"), 4. CTA, 5. Bonuses stacked AFTER the price to widen the value gap, 6. VIP as a side-by-side option if applicable, 7. The same post-price sequence (objections, guarantee, proof, choice, urgency, welcome).

**Validation checklist (lead agent writes `working/qc/price_sequence_check.md`, all boxes ticked before Phase 1Q):**
- [ ] Every stack component has a stated value; stack math sums to the anchor, and THE SAME TOTAL appears identically on every slide that states it (the proven deck shipped with $5,282 on the stack slide and $5,276+ on the recap slide; cross-slide numeric consistency is now a hard check).
- [ ] Anchor >= 3x the lowest ladder rung; the FINAL real price sits below the ladder for maximum contrast (drop mode).
- [ ] Ladder rungs placed at the proportional positions; every drop has a BUILDUP slide immediately before it and a stated earned reason; drops strictly decrease and end exactly at the client-approved `FINAL_PRICE`.
- [ ] Anchor slide contains the explicit memory hook; the offer section contains the callback line.
- [ ] Guarantee positioned after the final price reveal; bonuses per mode rules; VIP side-by-side with the final price.
- [ ] Scarcity/urgency claims are TRUE (real spots, real dates, real expiry); results claims carry the compliance disclaimer line.
- [ ] No fabricated proof; placeholders marked `[CLIENT TO SUPPLY]`.

---

## 6. PHASE 1Q + 1A: COPY QC GATE, THEN OWNER APPROVAL GATE

### 6.1 Phase 1Q: internal copy QC (agents, before the owner ever sees it)

**3 to 5 QC agents on Minimax (DeepSeek v4 Flash fallback), in parallel, non-overlapping slide ranges.** Each agent scores each assigned slide 1 to 10 per criterion. **>= 8.5 overall passes. Below 8.5 loops back to the writer automatically. The owner never sees sub-8.5 work.** Up to 3 revision loops, then escalate to the lead agent. Report: `working/qc/copy_qc_report.md`.

**COPY QC GUIDE:**
1. **One big idea (AUTO-FAIL on violation):** the slide makes exactly one point. A multi-idea slide is an automatic FAIL, not a deduction; the operator's rule is "one big idea per slide, multi-idea slide FAILS." If a slide carries two ideas, split it and re-QC. (Mechanical signal: more than 3 text blocks, or copy that cannot fit Section 5.1 limits without dropping a point, indicates more than one idea.)
2. **Limits honored:** headline <= 9 words, sub <= 18, <= 3 text blocks, bullet and stack limits per Section 5.1. Mechanical count, auto-fail if over.
3. **Template complete:** every field of the Section 5.2 template filled, including PRESENTER NOTE.
4. **Tone match:** the copy sounds like the chosen `TONE` (and `TARGET_FEELING`). A Tough Love deck with soft hedging language = fail.
5. **Arc integrity:** the slide does its section's job (a Painful Math slide quantifies, a Commitment slide contracts, a Secret slide shifts one belief).
6. **Value Equation present:** teach and offer slides identifiably move one of the four variables.
7. **Pitch rules:** stack/bonus/guarantee/scarcity rules from Section 5.4 followed; price checklist consistent.
8. **No fabrication:** every proof point traces to `PROOF_ASSETS` or is marked `[CLIENT TO SUPPLY]`.
8a. **Cross-slide numeric consistency:** every number that appears on more than one slide (stack total, anchor, prices, stats, counts) is IDENTICAL everywhere it appears. The QC agent compiles all repeated numbers and diffs them. The proven deck shipped with $5,282 on one slide and $5,276+ on another; this criterion exists because of that. Any mismatch = auto-fail for both slides.
8b. **Ladder integrity:** ANCHOR carries the memory hook, every DROP has a BUILDUP immediately before it and an earned reason, callbacks reference the anchor, FINAL sits below the ladder (drop mode).
9. **Reads aloud:** the PRESENTER NOTE plus headline flow naturally when spoken.
10. **No em dashes (auto-fail on sight; the em dash is the dead giveaway), no jargon the audience would not use, seventh-grade clarity on client-facing words.**
11. **HOOK COUNT (mechanical):** count the hook occurrences across the deck. Fewer than 7 = auto-fail. First occurrence after the 15% mark = fail. No dedicated hook slide = fail. Proof slides without a refrain where the story proves the hook = flag for revision.
12. **Doctrine compliance (Section 4.3):** promises pitched not products; every drop adds value (rule 3); both emotion AND logic served in the offer section (rule 5); cost-vs-value explicitly answered, priceless pitch used where outcomes are non-monetary (rule 6); light pitches woven (rule 7); appetizer not dinner (rule 8: a Secret that hands over the complete HOW = fail); at least one intrigue slide per section (rule 10); compare/contrast device present in every Secret (rule 11); a paid pitch exists (rule 14) unless the owner signed off on free-only.
13. **Slide-vs-script separation:** slide text does not duplicate the presenter note narration (rule 15).
14. **Text anchor variation:** no more than 2 consecutive slides share the same TEXT_ANCHOR (rule 16).
15. **Who says so / external proof present (rule 12):** the deck carries at least one third-party proof beat (case study, study, or white paper) woven between the drops. A deck whose every proof point is the client's own assertion with zero external corroboration FAILS this criterion. The Deep Research GP-8 zero-proof alert, if present, forces a fail here until the operator supplies or approves corroboration.
16. **Wall of Wins present (rule 20):** the deck carries a Wall of Wins / wall of results slide near the close that concentrates multiple named, located client wins in one view. Absent = fail.
17. **Guarantee present (rule 21):** the deck states an explicit guarantee / risk-reversal beat (one of the four types, Section 5.4). Absent = fail.
18. **Scarcity Factor present (rule 21):** the close carries a real scarcity / last-calls / doors-closing beat (real spots or real time only). Absent = fail; fabricated scarcity = blocking flag (handled by the Devil's Advocate).
19. **Story Arc present (rule 19):** the deck carries an explicit short-term-fix-vs-long-term-identity contrast beat that drives the audience to self-recognition. Absent = fail.

Weighting: criteria 1, 2, 7, 11, 12, and 15 count double. Any auto-fail (including a multi-idea slide under criterion 1) forces FAIL.

### 6.2 Phase 1A: OWNER APPROVAL GATE (human, mandatory, blocks Phase 2)

When ALL slides pass copy QC, present the full deck copy to the owner in readable form (the slides_copy.md content, cleanly formatted, via the client's normal channel) and ask exactly this:

> "Here is every slide, word for word, plus what you'll say on each one. **Do you approve the slides as written?** If not, tell me what you'd like changed and I'll revise."

- **Approve:** record approval (who, when, verbatim message) in `working/copy/approval_record.json`. Phase 2 may begin.
- **Changes requested:** revise the named slides, re-run copy QC on the changed slides only, re-present. Loop until approved.
- **NOTHING in Phase 2 onward starts before this approval exists.** An approval record with a timestamp is the gate token. No record, no prompts.

---

## 7. PHASE 2: WRITE ONE IMAGE PROMPT PER SLIDE

**Model: Kimi 2.6. Parallel writer agents with non-overlapping slide ranges (e.g., A: 1-20, B: 21-40, C: 41-60), all writing against the approved slides_copy.md and the shared STYLE BLOCK.** Output: `working/prompts/slide-NN.txt` per slide plus combined `working/prompts/all_prompts.md`.

**The proven method is ONE complete standalone prompt per slide.** The shared STYLE BLOCK (written once by the lead agent, ~800 to 1,500 chars: white base rule, the three brand hexes and roles, typography system, logo rule, mood keywords, representation rule, 16:9/2K line) is embedded inside every prompt. It supplements the per-slide spec; it never replaces it.

### 7.1 Length rules (hard limits)
- **MINIMUM 1,500 characters** (auto-fail under). **SOP MAXIMUM 15,000.** **TARGET 5,000 to 7,500.**
- The Kie.ai GPT Image 2 API hard ceiling is **20,000 characters** in `input.prompt` (roughly 3,000 to 3,300 words). The SOP maximum sits at 15,000 deliberately: a 5,000-character safety margin below the API ceiling so a prompt never gets rejected or truncated by the platform.
- FRONT-LOAD the critical content anyway: composition, background, verbatim headline, brand colors, logo placement first; mood and negative-space detail last. If KIE ever returns a length error, condense to the front-loaded essentials and LOG the truncation. Never silently drop detail.

### 7.2 Visual archetype library (THE FIVE PROVEN ARCHETYPES, from the Lyric 75-slide run)

The proven deck was built on exactly FIVE layout archetypes, rotated across all 75 slides. Every slide in Phase 1 is assigned one archetype (recorded in its slides_copy.md entry), and the prompt declares its archetype in its first line. Rotating five strong layouts beats inventing a new layout per slide: the deck stays coherent AND varied.

| Code | Archetype | Layout definition | Best for |
|---|---|---|---|
| A1 | FULL-BLEED PHOTO + HEADLINE OVERLAY | One emotionally precise photo fills the frame; a soft white-to-transparent gradient scrim sweeps one region (typically the bottom 25 to 30%, heaviest on one side); the text group sits on the scrim with a kicker label, headline, sub-head, and thin gold rule | Future-pacing, vision slides, story beats, BUILDUP slides before drops, section moments with high emotion |
| A2 | PHOTO ONE SIDE + TEXT OPPOSITE | Vertical split, roughly 45/55: a person or scene occupies one side; the opposite side is clean base color carrying the full text group (kicker, headline, sub, body lines, rules) | Origin story, authority, testimonials, objection handling, teach slides featuring a person |
| A3 | PHOTO-TOP / DATA-BOTTOM | Horizontal split: full-width photo band on top (40 to 58%), separated by a clean full-width 3px gold rule, with a data/type zone below on the base color carrying a giant number or structured data | Painful Math, big numbers, stats, before/after rows, stack tables, proof metrics |
| A4 | TYPE-DOMINANT PUNCH (+ optional image band) | Typography IS the slide: an enormous headline or number dominates; optional supporting photo band on top or behind; price tag motifs and strikethrough ladders live here | Big Bold Promise, ANCHOR, every price DROP, the FINAL price reveal, commitment and recap punches |
| A5 | PORTRAIT / SELFIE (image-to-image) | The client's REAL founder portrait (supplied photo passed as an additional input image) drives the slide; text group beside or below | Host intro, "I'm you" slides, guarantee (founder holding certificate), final push direct-to-camera |

**Composition language inside each archetype:** zones are described in PERCENTAGES of the frame ("top 58% photo band," "bottom 42% type zone") plus thirds language for element placement within zones. Both are required.

**Recurring brand devices (the proven deck's visual grammar, specify them explicitly):**
- Kicker label: small all-caps letter-spaced label in gold or pink above the headline, with a short gold rule beneath it.
- Gold 3px full-width rule as the divider between photo and type zones.
- Color roles: gold = money, value, and dividers; pink/accent = action, emphasis words, and urgency; charcoal = headlines (never pure black backgrounds).
- Price tag motif: drops are rendered as a large white hang-tag shape with a gold border; old prices in charcoal/gold struck through with DRAWN gold diagonal lines; the new price glowing in accent at the bottom of the tag.
- Section progress labels on section-opener slides ("SECTION 3 OF 7", "SECRET #1" in a filled accent banner box).
- Logo on a white chip (~9% of slide width, subtle 1px gold border) in the same corner on every slide.
- Compliance line: any results/income claim slide carries a small italic disclaimer ("Results will vary. Average student sees...") in the lower margin.

People-allocation rule: distribute `PEOPLE: yes` slides so the deck-wide ratio matches `REPRESENTATION_MIX` percentages and `VISUAL_MIX` density. The lead agent verifies the distribution before prompt QC.

### 7.3 Every prompt MUST contain (the full design spec)

1. **Format line:** "A 16:9 presentation slide, 2K resolution..."
2. **Background:** WHITE BASE, described with character (clean flat white, soft gradient to a pale brand-tinted edge), never just "white background." Dark backgrounds only with `DARK_OK = true`.
3. **Headline copy VERBATIM** from the approved slides_copy.md, character for character, with the EMPHASIS words and their accent treatment specified. Same for sub-copy and supporting text.
4. **Typography:** named font style (bold geometric sans such as Montserrat Black for headlines, lighter geometric sans for body), case, tracking, relative sizes. LARGE, CREATIVE font usage is a primary design element of this SOP: headlines render big, numbers render bigger, and font choices should feel editorial, not default.
5. **FONT PLACEMENT:** where every text element sits, in thirds language. Typeface-only with no position = QC fail.
6. **Thirds grid (required in every prompt):** top/middle/lower x left/center/right. State which thirds the headline occupies, which the sub-copy occupies, which any people or objects occupy. "Centered" alone is insufficient.
7. **OBJECT PLACEMENT:** every box, banner, ribbon, rule, badge, card, frame, or graphic object explicitly described: what it is, where it sits (thirds), its color, its style (filled/outlined, sharp/rounded, thin/bold).
8. **OVERLAYS (explicit language):** anything layered on top of a photo or illustration must say "overlaid": "a semi-transparent white text plate overlaid over the photo in the lower-right third." Unstated overlays render fused or side-by-side.
9. **Brand palette:** the exact intake hexes and exactly where each appears, always on the white base. Color scheming around faces and skin tones described explicitly and consistent with the palette.
10. **Logo:** position (consistent corner across the deck) plus a backdrop plate spec wherever contrast requires. Never a floating illegible logo. (Skip entirely if `LOGO_ON_SLIDES = false`.)
11. **People (when present), driven by the three engines:**
   - **FACIAL EXPRESSION ENGINE:** the face must match what the slide is SAYING. Every person spec includes hair (color, style, length), clothing (color, style, formality), and a facial expression described in terms of the emotion the slide communicates (a pain slide gets a worried, overwhelmed face; a vision slide gets the arrived, relieved smile). Missing any of the three = auto-fail.
   - **AUDIENCE ENGINE:** people match the slide's REPRESENTATION_MIX assignment and `AUDIENCE` (age group, gender mix, style of dress for the niche).
   - **WORLD ENGINE (real-world knowledge):** the SETTING matches the industry and the moment. Where would this person actually be: their office, the kitchen table at dinner, the empty classroom at 6am? Every people-slide prompt states the real-world setting and why it fits the slide's idea. A generic studio backdrop where a real-world scene belongs = fail.
12. **Bullets when necessary:** bullet slides specify the chip/glyph style, spacing, and alignment explicitly (L1 archetype).
13. **Mood + lighting:** emotional tone and lighting language ("clean, evenly lit, premium daylight studio feel").
14. **Professionalism bar:** the prompt reads like an art director's brief for a work of professional visual art, not a clip-art slide.
15. **Closing constraints:** "16:9 aspect ratio. 2K quality. Presentation slide." plus negatives (no watermarks, no misspellings, no cartoon clipart).

### 7.4 Strikethrough prices and struck-through text (special handling, required)

Image models render strikethrough unreliably. For every DROP/FINAL ladder slide and any struck-through reframe, prompts MUST describe the strike as a drawn object, not a font style: "the old price '$9,997' rendered in muted gray with a single bold straight horizontal line in [BRAND_ACCENT] drawn cleanly through the center of the numerals, the line slightly wider than the text." Image QC checks the strike rendered as a clean single line through the text. If two generation attempts both fail the strike, the fallback is approved: generate the slide WITHOUT the old price text and add the struck-through old price as a native PPTX text box during Phase 6 assembly (logged in `working/checkpoints/pptx_text_overlays.json`). Native text overlay is the documented fallback for ANY slide whose verbatim text fails twice on render.


### 7.5 GOLD-STANDARD EXEMPLAR PROMPT (the REAL Slide 1 from the proven run)

This is the actual prompt that produced the title slide of the QC-9.42 Lyric deck, verbatim. Writer agents read this BEFORE writing. Every prompt produced must match this density, this structure, and this level of art direction, adapted to its own slide, archetype, and brand variables. Note the anatomy: the header block (title, ARCHETYPE / SECTION / LADDER tags, ONE BIG IDEA line), zone percentages, emotionally precise photo direction, exact verbatim copy with per-line font/size/color, the gold rule devices, the logo chip spec, MOOD + LIGHTING, and the closing COLOR VERIFICATION and AVOID blocks.

```
### SLIDE 1: Fill 30 Seats In 30 Days
[ARCHETYPE 4] [SECTION: THE HOOK] [LADDER: none]
ONE BIG IDEA: An audacious, specific promise - 30 seats, 30 days, zero ad spend.
PROMPT:
Archetype 4 - TYPE-DOMINANT PUNCH with supporting image band. 16:9 canvas. Base: warm off-white #FBF7F4 full frame. NO black backgrounds anywhere.

LAYOUT: Top 58% of the slide is a bright, airy full-width photo band. Bottom 42% is the type-dominant punch zone on warm off-white #FBF7F4.

PHOTO BAND (top 58%, full-width): A modern, light-filled daycare interior hallway or wide classroom corridor photographed from a low-angle, slightly wide lens. Eight to twelve child-sized cubbies and coat hooks run along a bright white-painted wall - every single hook carries a tiny colorful backpack, every cubby is full of lunchboxes and extra clothes. Warm natural sunlight streams through a wide bank of windows on the right side of the corridor; the light is mid-morning gold. On the far left of the frame, just barely visible and intentionally soft-focused, the blurred silhouette of a confident Black woman in a tailored raspberry-pink (#C8104E) blazer stands with arms loosely crossed, head slightly tilted, half-smiling - she is watching her full center. She is NOT the focus; the FULL cubbies are the hero. The mood: abundant, joyful, DONE - this is what full looks like. Premium lifestyle-documentary photography. No clipart, no cartoons, no cheesy daycare stock imagery. No institutional overhead fluorescent lighting. Real life, warm and aspirational. Depth of field: cubbies crisp in the foreground, hallway softly blurred toward the background.

The photo band is separated from the type zone below it by a clean horizontal line in metallic gold (#C9A24B, 3px full-width), functioning as a premium visual divider.

TYPE ZONE (bottom 42%, warm off-white #FBF7F4 background):

Headline - centered, Montserrat Black, very large (approximately 78–86pt relative to slide height), two lines:
Line 1: "30 SEATS." - color: charcoal #231F20
Line 2: "30 DAYS." - color: charcoal #231F20
The two lines sit tight together, dominating the zone. They are the first thing the eye reads.

Sub-headline directly below, Montserrat ExtraBold, approximately 26–30pt, raspberry-pink #C8104E, centered:
"Even if you've never run a single ad in your life."

A thin horizontal rule in metallic gold #C9A24B (approximately 55% of the slide width, centered) sits between the sub-headline and the tertiary line below it - a premium breathing line.

Tertiary line, Montserrat Medium, approximately 17–19pt, charcoal #231F20, centered, set in italics:
"- The Enrollment On Autopilot Method -"

LOGO: "7 Figure Childcare CEO" logo placed in the bottom-right corner of the type zone, approximately 9% of slide width, on a clean crisp white rectangular chip with a subtle 1px gold border (#C9A24B). Logo never recolored, never distorted, never clipped.

MOOD + LIGHTING: Hopeful, electric, big-promise energy. The image says "this is real and it's already happening somewhere." The type says "I will tell you exactly how." Not motivational-poster vague - specific, credible, aspirational.

COLOR VERIFICATION: White/off-white base confirmed throughout. Pink #C8104E on sub-headline. Gold #C9A24B on rule, divider, and logo chip border. Charcoal #231F20 on main headline and tertiary line. Zero black backgrounds anywhere in the frame.

AVOID: Deformed hands or extra fingers. Garbled text elements. Clipart or cartoon daycare graphics. Black backgrounds. Men as the focal figure. Cheesy stock photography. Institutional fluorescent lighting. Dark, moody, or desaturated tones.
```

**Mandatory prompt anatomy (every prompt, in this order):**
1. Header: slide title, `[ARCHETYPE n] [SECTION: ...] [LADDER: ...]` tags, and a ONE BIG IDEA line.
2. Archetype declaration + canvas line + base color + "NO black backgrounds anywhere."
3. Zone layout in percentages, then element placement in thirds within zones.
4. Photo/scene art direction: emotionally precise, documentary-premium language; the photo must TELL the slide's one idea (empty chairs ARE the story).
5. Verbatim text groups: every line quoted exactly, each with font, weight, relative point size, color hex, alignment, and position.
6. Brand devices: kicker label, gold rules, dividers, tags, banner boxes, chips, all explicitly described.
7. Logo chip spec.
8. MOOD + LIGHTING paragraph.
9. COLOR VERIFICATION block: restates every hex and its role, confirms the base, confirms zero black backgrounds.
10. AVOID block: deformities, garbled text, clipart, black backgrounds, stock-photo cheese, plus slide-specific negatives.

---

## 8. PHASE 3: PROMPT QC GATE (before ANY image is generated)

**5 to 10 QC agents (minimum 5, maximum 10) on Minimax, DeepSeek v4 Flash fallback, fired SIMULTANEOUSLY.** Distribute prompts so every prompt is scored by TWO different agents; the lead agent adjudicates when the two scores straddle 8.5. Single-scorer QC against a hard threshold is noisy; dual scoring is the standard.

**>= 8.5 = PASS. < 8.5 or any auto-fail = FAIL, automatically looped back to the writer for revision and re-QC, without owner involvement.** Up to 3 attempts, then escalate to the lead agent. Zero createTask calls until every prompt has passed. Report: `working/qc/prompt_qc_report.md` (per-prompt scores from both scorers, character counts, verdicts, revision notes).

### PROMPT QC GUIDE (score each criterion 1 to 10)

**CHECK 0, HARD LENGTH GATE (run first, mechanically):** count the characters. Under 1,500 = automatic fail, stop scoring. Over 15,000 = automatic fail. Record the exact count.

1. **Detail and length in range:** full design spec present (composition, typography, layout, mood, lighting); target 5,000 to 7,500.
2. **Brand palette + WHITE BASE:** intake hexes present and correctly assigned; background explicitly white/light AND characterized beyond one word. Any dark-background language without `DARK_OK` = auto-fail.
3. **Copy verbatim:** headline, sub-copy, and supporting text match the APPROVED slides_copy.md character for character, emphasis words specified. Paraphrase = auto-fail.
4. **16:9 + 2K stated:** both present. Missing either = auto-fail.
5. **No dark styling anywhere** (moody/noir/black-luxury language) unless `DARK_OK`.
6. **Logo handled:** placement + contrast plate where needed (or correctly absent if `LOGO_ON_SLIDES = false`).
7. **Engines satisfied:** correct REPRESENTATION_MIX group (Audience Engine); hair + clothing + facial expression ALL described and the expression matches the slide's emotion (Facial Expression Engine); the real-world setting stated and industry-appropriate (World Engine); face/skin color scheming consistent with palette. Missing any = auto-fail. ("No people" stated when none.)
8. **Thirds language present:** explicit thirds placement for headline, supporting copy, people/objects, imagery. Absent = auto-fail.
9. **Background characterized,** not just named.
10. **Font placement explicit:** position, not just typeface.
11. **Objects described:** every box/banner/ribbon/badge/card: what, where, color, style.
12. **Overlays explicit:** "overlaid" language wherever layering occurs.
13. **Professionalism / typography bar:** reads as art direction; large creative type usage specified; generic "clean text" = fail. (Double weight.)
14. **Archetype followed:** the prompt declares and matches its assigned A1-A5 archetype (Section 7.2), uses the brand devices (kicker, gold rules, chips, tag motif), and handles strikethrough as drawn lines per Section 7.4 on every drop slide.
15. **Internal consistency + render safety:** style block embedded, no contradictions, text quantity renderable within Section 5.1 limits.

Weighting: criteria 2, 3, 4, 13 count double. Any auto-fail forces FAIL regardless of average.

---

## 9. PHASE 4: IMAGE GENERATION (KIE.AI, GPT-IMAGE-2 HARDCODED)

**One dedicated submission agent owns this phase.** A single agent is what makes the rate cap enforceable.

### 9.0 The MODEL MANIFEST (declared up front, the single place a model ever changes)
At the ECHO (Section 3.3), the agent declares the model manifest for the run and the operator confirms it. The manifest is the ONLY place an image model is named; every later phase reads from it.

```json
{
  "image_platform": "kie.ai",
  "image_model_t2i": "gpt-image-2-text-to-image",
  "image_model_i2i": "gpt-image-2-image-to-image",
  "resolution": "2K",
  "aspect_ratio": "16:9",
  "authorized_by": "<operator>",
  "date": "<run date>"
}
```
- Saved to `working/checkpoints/model_manifest.json`.
- **The platform is Kie.ai and the model family is GPT Image 2. Period.** No fallback model, no "equivalent," no substitution on error, mid-run. An outage = pause and escalate.
- **Flexibility lives here and only here:** when a newer GPT Image 2 version (or a different model the operator prefers) ships, the operator updates the manifest in writing, and the whole pipeline follows. Agents never improvise a model change; they propose one at echo time and the operator decides.

### 9.1 Which variant, when
- **Image-to-image (`gpt-image-2-image-to-image`)** is the proven default when `LOGO_ON_SLIDES = true`: every call passes `input_urls` beginning with `LOGO_URL` so the logo lands on every slide, and the prompt carries a STRICT no-redesign instruction: "reproduce this logo pixel-for-pixel, do not redesign, recolor, re-letter, or re-monogram it." This keeps ONE canonical logo lockup across the whole deck (the model must never invent a fresh logo or a monogram variant per slide). `input_urls` accepts up to **16 public https URLs**, which is how the A5 founder-portrait archetype works: pass `[LOGO_URL, FOUNDER_PORTRAIT_URL]` (and optionally a style-reference slide image), and the prompt states which reference is which ("the first image is the logo, the second is the founder whose likeness drives the portrait"). Optionally composite ONE canonical logo PNG identically post-render as a belt-and-suspenders.
- **OFFER-SLIDE PRICE == FINAL_PRICE (assert):** the price shown on the offer / CTA slide must equal `FINAL_PRICE` from the intake / price ladder. A deck whose offer slide shows any number other than `FINAL_PRICE` fails final-deck QC (this catches the $544-where-it-should-be-$97 class of error). Cross-slide numeric consistency already gates repeated numbers; this is the explicit offer-slide assert on top of it.
- **Text-to-image (`gpt-image-2-text-to-image`)** only when there are no reference images at all (`LOGO_ON_SLIDES = false` and no portrait), with no `input_urls` field in the body.

### 9.2 Rate cap
- **Never more than 20 requests per 10 seconds (2 RPS).** REQUEST rate, not tokens.
- Proven safe pattern: waves of 20 submissions, then sleep 15 seconds, repeat. Retries count against the cap.
- Pipelined: submit wave N+1 as soon as the 15-second window clears; do not wait on wave N's render results.

### 9.3 Submit (async createTask)
- `POST https://api.kie.ai/api/v1/jobs/createTask`
- Headers: `Authorization: Bearer $KIE_API_KEY` (the CLIENT'S key), `Content-Type: application/json`
- Image-to-image body (the default; model strings come from the manifest):
```json
{
  "model": "gpt-image-2-image-to-image",
  "input": {
    "prompt": "<the slide's full QC-passed prompt>",
    "input_urls": ["<LOGO_URL>", "<FOUNDER_PORTRAIT_URL if A5>"],
    "aspect_ratio": "16:9",
    "resolution": "2K"
  }
}
```
- Text-to-image body (no reference images): model `gpt-image-2-text-to-image`, same `input` minus `input_urls`.
- **API hard limits:** `input.prompt` max **20,000 characters**; `input_urls` max **16** public https URLs; resolutions `1K | 2K | 4K`; aspect ratios include `16:9` (this SOP pins 16:9 / 2K via the manifest). An optional `callBackUrl` webhook exists; this SOP polls instead, since client boxes rarely expose a public callback endpoint.
- On `{ "code": 200, "data": { "taskId": "..." } }`: append `{ "slide_NN": "<taskId>" }` to `working/checkpoints/kie_task_ids.json` after EACH success.
- Retry each individual submit up to 3x on non-200, logging `failCode`/`failMsg` when present. Length rejection: condense front-loaded, log the truncation, resubmit.

### 9.4 Polling (loop-guarded, exactly this schedule)
- After the LAST submission, **wait 5 minutes**, then run the first poll pass.
- Then **poll every 1 minute**.
- `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>` (same Bearer auth). Parse `data.state`: the documented values are `waiting` | `success` | `fail` (treat any of `fail`/`failed`/`error`/`cancelled` as terminal failure for robustness). On failure, log `data.failCode` and `data.failMsg` to the checkpoint for diagnosis.
- On `success`: parse `data.resultJson` (a JSON STRING) -> `resultUrls` array -> download `resultUrls[0]` to `working/renders/slide-NN.png`. Note it is `resultUrls`, an array, NOT a `.url` field; the older runbook had this wrong. All downloads in a completed pass run in parallel.
- **HARD CAP: 100 poll passes maximum per generation run.** Hitting 100 with tasks still `waiting` means STOP polling, checkpoint everything, and escalate to the lead agent with the list of stuck task IDs. Never loop forever.
- Save `working/checkpoints/poll_results.json` after every pass. `failed` tasks: resubmit (within the rate cap), up to 3 attempts per slide, then flag.

### 9.5 Reference implementation (the submitter and poller, adapt as needed)

```python
import json, time, requests, pathlib

KEY = os.environ["KIE_API_KEY"]          # client's own key
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
BASE = "https://api.kie.ai/api/v1/jobs"
CKPT = pathlib.Path("working/checkpoints")

def submit_all(prompts: dict, logo_url: str):
    tasks = json.loads((CKPT/"kie_task_ids.json").read_text()) if (CKPT/"kie_task_ids.json").exists() else {}
    pending = [(s, p) for s, p in sorted(prompts.items()) if s not in tasks]
    for i in range(0, len(pending), 20):              # waves of 20
        for slide, prompt in pending[i:i+20]:
            body = {"model": "gpt-image-2-image-to-image",
                    "input": {"prompt": prompt, "input_urls": [logo_url],
                              "aspect_ratio": "16:9", "resolution": "2K"}}
            for attempt in range(3):
                r = requests.post(f"{BASE}/createTask", headers=H, json=body, timeout=60)
                if r.ok and r.json().get("code") == 200:
                    tasks[slide] = r.json()["data"]["taskId"]
                    (CKPT/"kie_task_ids.json").write_text(json.dumps(tasks, indent=2))
                    break
                time.sleep(2)
        time.sleep(15)                                # rate-cap margin
    return tasks

def poll_all(tasks: dict, out_dir="working/renders"):
    time.sleep(300)                                   # 5-minute initial wait
    done, polls = {}, 0
    while len(done) < len(tasks) and polls < 100:     # 100-poll hard cap
        polls += 1
        for slide, tid in tasks.items():
            if slide in done: continue
            r = requests.get(f"{BASE}/recordInfo", headers=H, params={"taskId": tid}, timeout=60)
            state = r.json().get("data", {}).get("state")
            if state == "success":
                urls = json.loads(r.json()["data"]["resultJson"])["resultUrls"]
                img = requests.get(urls[0], timeout=120).content
                pathlib.Path(f"{out_dir}/{slide.replace('_','-')}.png").write_bytes(img)
                done[slide] = "success"
            elif state in ("fail", "failed", "error", "cancelled"):
                d = r.json().get("data", {})
                done[slide] = f"fail:{d.get('failCode')}:{d.get('failMsg')}"  # resubmit upstream
        (CKPT/"poll_results.json").write_text(json.dumps({"polls": polls, "done": done}, indent=2))
        if len(done) < len(tasks): time.sleep(60)     # 1-minute interval
    if polls >= 100 and len(done) < len(tasks):
        raise RuntimeError(f"POLL CAP HIT: stuck tasks {set(tasks)-set(done)}; escalate")
    return done
```

Run this detached (nohup / background session) with checkpoints; resume by re-reading `kie_task_ids.json` and `poll_results.json`.

---

## 10. PHASE 5: IMAGE QC GATE

**The same 5 to 10 QC agents, fired simultaneously, dual-scored exactly like prompt QC.** **>= 8.5 passes. Below 8.5 loops back automatically, never to the owner.**

### 10.1 The fail branch (diagnose BEFORE looping)
Not every failed image means a bad prompt. The QC verdict must classify the failure:
- **RENDER NOISE** (garbled hand, one misspelled word, glyph artifact, but the prompt clearly specified it correctly): REGENERATE the same prompt as-is. Do not rewrite, do not re-run prompt QC. Counts as a generation attempt.
- **PROMPT DEFECT** (wrong composition, wrong colors, missing element the prompt failed to specify): revise the prompt (targeting the specific failure), re-run prompt QC on that prompt only, regenerate.
- **TEXT RENDER FAILURE x2** (verbatim text garbled on two attempts): invoke the Section 7.4 fallback: regenerate without the failing text element and add it as a native PPTX text box at assembly. Log it.

Maximum 3 generation attempts per slide, then escalate.

### 10.2 Generation budget (deck-wide cap)
Total generations for the run are capped at **2x SLIDE_COUNT** (e.g., 120 generations on a 60-slide deck). At 1.5x, the submission agent posts a budget warning to the lead agent. At 2x, generation STOPS and the lead agent escalates to the operator with the failure analysis. No silent money fires.

### 10.3 IMAGE QC GUIDE (score each criterion 1 to 10)
1. **Matches the prompt:** composition, archetype, and elements as specified.
2. **Brand colors correct,** no off-brand cast, face/skin scheming consistent.
3. **WHITE BASE** (auto-fail dark unless `DARK_OK`).
4. **No dark styling,** bright clean premium overall.
5. **Text legible AND correct:** every word matches the approved verbatim copy; any misspelling, duplicated word, or garbled glyph = auto-fail; readable from presentation distance.
6. **Logo right:** present (when required), placed, undistorted, legible, plate rendered as specified. Missing/mangled = auto-fail.
7. **16:9** (auto-fail if wrong).
8. **2K quality:** no artifacts, no blur on text edges.
9. **Representation + expression correct:** people match the slide's assigned group; the FACIAL EXPRESSION matches the slide's emotion (a smiling face on a pain slide = fail); the real-world setting matches the prompt; no deformities (hands, faces, limbs) = auto-fail; no people when none specified.
9a. **No emojis/clipart icons** rendered into a premium deck; photographic or typographic treatment only = anything else fails.
9b. **No em dashes rendered in slide text** = auto-fail.
10. **Object/overlay fidelity:** boxes, plates, rules, strikethrough lines rendered as drawn objects per the prompt; overlays actually overlaid.
11. **Slide-worthiness:** one idea, bold, consistent with the deck.

Weighting: 3, 5, 6, 7 double. Any auto-fail forces FAIL.

### 10.4 Passes move immediately
The moment a pass verdict lands: copy to `media-library/slide-NN.png` AND upload to the client's GHL media library folder as `Slide NN v<N>`. Do not batch-hold passed images. Record GHL file IDs and URLs in `working/checkpoints/ghl_upload_report.md` as they land.

---

## 11. PHASE 6: ASSEMBLY, FINAL QC, DELIVERY

### 11.1 Completeness check
`media-library/` contains exactly `SLIDE_COUNT` files, `slide-01.png` through `slide-NN.png`, zero gaps. A gap = an unfinished QC loop; go back. Every passed image is confirmed in GHL.

### 11.2 PPTX assembly (python-pptx, with speaker notes)
```python
from pptx import Presentation
from pptx.util import Inches, Pt
import pathlib, json

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
blank = prs.slide_layouts[6]
notes = json.loads(pathlib.Path("working/copy/presenter_notes.json").read_text())
overlays = json.loads(pathlib.Path("working/checkpoints/pptx_text_overlays.json").read_text())

for img in sorted(pathlib.Path("media-library").glob("slide-*.png")):
    n = img.stem                                  # "slide-07"
    slide = prs.slides.add_slide(blank)
    slide.shapes.add_picture(str(img), 0, 0, width=prs.slide_width, height=prs.slide_height)
    for ov in overlays.get(n, []):                # Section 7.4 native-text fallback
        tb = slide.shapes.add_textbox(Inches(ov["x"]), Inches(ov["y"]), Inches(ov["w"]), Inches(ov["h"]))
        run = tb.text_frame.paragraphs[0].add_run(); run.text = ov["text"]
        run.font.size = Pt(ov["pt"]); run.font.bold = ov.get("bold", True)
        if ov.get("strike"): run.font._rPr.set("strike", "sngStrike")
    slide.notes_slide.notes_text_frame.text = notes.get(n, "")

prs.save("<Deck_Title>_v<N>.pptx")
```
The PRESENTER NOTE field from every slide entry is exported to `presenter_notes.json` at the end of Phase 1A (the approved copy) and lands in the PPTX speaker notes here. The deck ships WITH its script.

### 11.3 Final deck QC (>= 8.5, and here is HOW)
Agents cannot eyeball a PPTX directly. Render it first:
```
soffice --headless --convert-to pdf <Deck>.pptx && pdftoppm -png -r 100 <Deck>.pdf working/qc/finalrender/page
```
One QC agent reviews the rendered pages end to end: order correct, no duplicates or gaps, full-bleed and undistorted, native text overlays positioned correctly, branding consistent, the narrative and price sequence read correctly start to finish, speaker notes present. Score it; below 8.5 = fix and re-assemble. Record in `working/qc/final_deck_qc.md`.

### 11.4 Delivery (ask, do not assume)
1. **If the client is on a Mac (Mac mini etc.):** copy the PPTX to their **Downloads** folder, upload to their GHL media library, mirror to Drive if applicable, and tell them exactly where it is: "Your deck is in your Downloads folder as <name>.pptx, and also in your GHL media library under <folder>."
2. **If not, or if the environment is unclear: ASK.** "Where would you like the PowerPoint delivered: email, Google Drive, GHL, or somewhere else?" Then deliver there.
3. **Verify with ground truth:** confirm the file exists at every destination (ls / API fetch) before reporting done. A "done" message without verified artifacts is a lie.
4. Notify via the client's normal channel (`openclaw message send`, never raw Telegram API) with locations and the final QC score.



### 11.5 PHASE 7: RESILIENCE CRON (self-healing, from the proven runbook)

Long runs stall: agents die, polls hang, sub-agents silently stop writing. The proven run used a watchdog and so does this SOP.

1. At the start of Phase 4, create a cron that fires **every 10 minutes for 90 minutes** (or until the job reports DONE).
2. Each tick checks that the lead agent and every sub-agent (submission agent, QC agents) are alive AND progressing: a heartbeat file or the last-write timestamp on the progress JSONs (`kie_task_ids.json`, `poll_results.json`, QC reports) must be newer than the previous tick.
3. A stage with no progress in 10 minutes is STALLED: the cron resumes it from its last checkpoint. Checkpoint files make every phase idempotent; a resumed phase skips completed items. Never restart from scratch; always resume.
4. The cron stops when the PPTX exists, is uploaded, and the delivery notification has been sent.
5. Every cron tick appends one line to `working/checkpoints/watchdog.log` (timestamp, stage states, action taken).

---

## 12. EXECUTION STRATEGY: PARALLELIZE EVERYTHING THAT CAN BE

Serial one-at-a-time execution is a failure mode. Mandatory defaults:
- **Copy writing:** one writer agent for short decks; section-split parallel writers for 60+ slide decks (lead agent owns arc continuity and writes the offer section itself).
- **Prompt writing:** multiple writer agents, non-overlapping slide ranges, shared STYLE BLOCK written once by the lead.
- **All QC phases:** agents fired simultaneously, dual-scored, lead adjudicates.
- **Generation:** waves of 20, pipelined with polling; downloads in parallel.
- **What MUST stay sequential:** Step 0 before everything; copy before prompts; copy QC before owner approval; OWNER APPROVAL before any prompt; prompt QC gate before any generation; image QC gate before assembly. Everything else: parallel.

**Resumability rule:** every phase checkpoints the moment an item completes. On restart, read checkpoints, skip done work, resume exactly where it stopped. Never restart a run from scratch.

---

## 13. MASTER CHECKLIST (tick every box, in order)

```
STEP 0 - LANDING ZONES (FIRST ACTION)
[ ] 0.1  Local workdir created: ~/webinar-decks/<client>/<deck>/<YYYY-MM-DD>/ + all subdirs
[ ] 0.2  GHL media library folder created (or root+prefix fallback logged)
[ ] 0.3  Drive mirror folder created if applicable; media_library.json written
[ ] 0.4  Client's own KIE / Ollama Cloud (or OpenRouter) / GHL keys located and live-tested
[ ] 0.5  Model routing recorded in models_used.json (incl. Minimax version, fallbacks)

STEP 0.5 - CAPACITY
[ ] 0.5a Capacity probe run (RAM/CPU/disk/load, cloud reachability, Kie credits, token balances)
[ ] 0.5b Fleet sized per the table; capacity_plan.json written; budget shortfalls escalated BEFORE starting

PHASE A - DISCOVERY (3 to 10 questions, adaptive)
[ ] A.1  Known answers skipped; only unknowns asked; question count between 3 and 10
[ ] A.2  GOAL + CTA_ACTION + TARGET_FEELING captured
[ ] A.3  TONE chosen from the seven styles (or blend)
[ ] A.4  PRICE_MODE (drop|straight) + full offer stack, anchor, final price, payment plan
[ ] A.5  VIP_TIER decision (+ contents, price, real spot count if yes)
[ ] A.6  DURATION_MIN captured
[ ] A.7  Brand hexes + LOGO_ON_SLIDES + LOGO_URL verified downloadable
[ ] A.8  REPRESENTATION_MIX with PERCENTAGES + VISUAL_MIX captured
[ ] A.9  PROOF_ASSETS collected; CLIENT_NOTES verbatim; DARK_OK recorded (default false)
[ ] A.10 Full intake echoed to client and CONFIRMED; intake.json written
[ ] A.11 ECHO PROTOCOL complete: mission echoed, PRD + agent's own checklist (list of promises) produced,
         improvement pass listed, operator said GO; operating MODE (A scratch | B enhancement) declared
[ ] A.12 Mode B only: gap analysis of the existing deck reported and approved BEFORE any change;
         client's words preserved verbatim throughout

PHASE B - SLIDE MATH
[ ] B.1  SLIDE_COUNT set from the duration table; hard max respected (90 absolute ceiling)
[ ] B.2  Allocation reconciled to exact SLIDE_COUNT (adjust Secrets, never the offer section)
[ ] B.3  One big idea per slide confirmed as the governing rule

PHASE 1 - SLIDE COPY
[ ] 1.1  Every slide written in the Section 5.2 template, incl. PRESENTER NOTE
[ ] 1.2  Hard copy limits honored (9-word headlines, 18-word subs, <= 3 blocks, bullet/stack caps)
[ ] 1.2a HOOK derived and sung >= 7 times; first occurrence inside the first 15%; dedicated hook slide;
         refrains after proof; reprise in the close; occurrences tagged
[ ] 1.2b Doctrine honored (4.3): promises not products; every drop ADDS value; emotion + logic both served;
         cost-vs-value answered (priceless pitch where non-monetary); light pitches woven; appetizer not dinner;
         one pain per slide with emotional imagery; intrigue slide per section; compare/contrast in every Secret;
         a paid pitch exists; slide text never duplicates the script; text anchors vary
[ ] 1.3  Archetype (A1-A5) + LADDER tag assigned per slide; PEOPLE allocation matches REPRESENTATION_MIX + VISUAL_MIX
[ ] 1.4  Value Equation applied across Secrets and offer; stack/bonus/guarantee/naming rules followed
[ ] 1.5  Price sequence written per PRICE_MODE; SPREAD LADDER placed (rungs ~32/47/68/87/97%);
         ANCHOR memory hook + BUILDUP before every DROP + callbacks written; price_sequence_check.md all boxes ticked
[ ] 1.5a Flow rules (4.2) honored: section banners, claim->proof within 2 slides, open loops closed, compliance lines on results claims
[ ] 1.5b Cross-slide numeric consistency verified (every repeated number identical everywhere)
[ ] 1.5c TEN REQUIRED COMPONENTS present (Section 4.4): the Promise leads; the Hook sung >=7x; at least one "who says so" external-proof beat woven between the drops (zero external proof = fail); a Wall of Wins slide near the close; one big idea per slide (multi-idea = auto-fail); an explicit Guarantee beat; a real Scarcity / last-calls beat in the close; a short-term-fix-vs-long-term-identity Story Arc beat; the spread price ladder; and the agent's own checklist-of-promises walked
[ ] 1.6  No fabricated proof; placeholders marked [CLIENT TO SUPPLY]

PHASE 1Q - COPY QC (internal, automatic)
[ ] 1Q.1 3 to 5 QC agents in parallel; every slide scored per the COPY QC GUIDE
[ ] 1Q.2 All slides >= 8.5 (sub-8.5 looped back WITHOUT owner involvement); copy_qc_report.md written

PHASE 1A - OWNER APPROVAL GATE (human, blocking)
[ ] 1A.1 Full deck copy presented readably; approval question asked verbatim
[ ] 1A.2 Changes looped (revise -> re-QC changed slides -> re-present) until approved
[ ] 1A.3 approval_record.json written (who, when, message); presenter_notes.json exported
[ ] 1A.4 ZERO prompts written before this record exists

PHASE 2 - PROMPTS
[ ] 2.1  STYLE BLOCK written once by lead; REAL exemplar (7.5) read by every writer agent;
         every prompt follows the 10-part anatomy incl. ONE BIG IDEA, COLOR VERIFICATION, AVOID blocks
[ ] 2.2  Parallel writers, non-overlapping ranges; one complete prompt per slide
[ ] 2.3  Every prompt 1,500 to 15,000 chars (target 5,000 to 7,500); approved copy VERBATIM
[ ] 2.4  Every prompt: white base characterized, hexes, thirds grid, font placement,
         object placement, explicit overlays, people spec (hair+clothing+expression),
         logo + plate (or absent per intake), archetype followed, 16:9 + 2K stated
[ ] 2.5  Every DROP/FINAL strikethrough described as a DRAWN gold line per Section 7.4 (price-tag motif)

PHASE 3 - PROMPT QC GATE
[ ] 3.1  5 to 10 agents simultaneous; DUAL scoring per prompt; Check 0 character count recorded
[ ] 3.2  Every prompt >= 8.5; fails auto-looped (max 3) then escalated; prompt_qc_report.md written
[ ] 3.3  ZERO generation before the full gate passes

PHASE 4 - GENERATION
[ ] 4.0  MODEL MANIFEST declared at echo, operator-confirmed, saved (Kie.ai + GPT Image 2 family pinned;
         any version/model change happens ONLY here, in writing)
[ ] 4.1  Correct variant used per manifest: gpt-image-2-image-to-image with input_urls (logo, + founder
         portrait on A5, max 16 refs) or gpt-image-2-text-to-image when no references. NOTHING else
[ ] 4.2  Rate cap honored: waves of 20, 15s sleeps, retries counted, single submission agent
[ ] 4.3  Task IDs checkpointed after EACH success; submission pipelined with polling
[ ] 4.4  Polling: 5-min initial wait, then every 1 minute, HARD CAP 100 polls, then escalate
[ ] 4.5  resultJson parsed as resultUrls ARRAY; renders downloaded in parallel; fails logged with
         failCode/failMsg and resubmitted (<= 3) or flagged
[ ] 4.6  Generation budget enforced: warn at 1.5x SLIDE_COUNT, STOP at 2x

PHASE 5 - IMAGE QC GATE
[ ] 5.1  Same agents, simultaneous, dual-scored; every image judged per the IMAGE QC GUIDE
[ ] 5.2  Fails CLASSIFIED first: render noise -> regenerate as-is; prompt defect -> revise + re-QC + regen;
         text fail x2 -> native PPTX text overlay fallback logged
[ ] 5.3  Every image >= 8.5 (sub-8.5 looped WITHOUT owner involvement; max 3 attempts then escalate)
[ ] 5.4  Passes moved IMMEDIATELY to media-library/slide-NN.png AND uploaded to GHL as "Slide NN v<N>"
[ ] 5.5  Expressions match slide emotion; settings match the World Engine spec; zero emojis; zero em dashes
[ ] 5.6  image_qc_report.md + ghl_upload_report.md written

PHASE 6 - ASSEMBLY + DELIVERY
[ ] 6.1  media-library complete: SLIDE_COUNT files, zero gaps; GHL uploads confirmed
[ ] 6.2  PPTX built (13.333x7.5, full-bleed, ordered, text overlays applied, SPEAKER NOTES embedded)
[ ] 6.3  Final deck QC via soffice->PDF->PNG render review; >= 8.5; final_deck_qc.md written
[ ] 6.4  Delivery: Mac -> Downloads + told where; otherwise ASKED where (email/Drive/etc.) and delivered
[ ] 6.5  Existence VERIFIED at every destination before reporting done
[ ] 6.6  Client notified via openclaw message send with locations + final QC score

PHASE 7 - RESILIENCE
[ ] 7.1  Watchdog cron created at Phase 4 start (every 10 min, 90 min, or until DONE)
[ ] 7.2  Stalled stages resumed from checkpoints (never restarted); watchdog.log written
[ ] 7.3  Cron stopped after verified delivery
```

---

## 14. MISTAKES TO AVOID (earned the hard way)

1. **Dark slides.** The first proven deck was built on black and had to be redone. White base, bright and clean, always, unless `DARK_OK = true`. Both QC guides auto-fail dark.
2. **Wrong aspect ratio / quality.** 16:9 and 2K stated in every prompt AND in the API fields. Auto-fail.
3. **Generating before prompt QC.** Burned generations on flawed prompts cost real money. The gate is absolute.
4. **One global style prompt for all slides.** Produces generic mismatched slides. One full prompt per slide; the style block lives inside each.
5. **Skipping Step 0.** Without the landing zones, passed images scatter and get lost.
6. **Blowing the rate cap.** Waves of 20, 15-second sleeps, one submission agent. RPS, not TPS.
7. **Switching image models on error.** Retry or escalate, never substitute. Operator authorization only.
8. **Skipping the owner approval gate.** Writing prompts against unapproved copy means rewriting prompts when the owner changes a word. Copy is approved FIRST, verbatim into prompts SECOND.
9. **Paraphrased headlines.** Image models render what you give them. Verbatim or auto-fail.
10. **Trusting `success` without QC.** Misspellings, mangled hands, and missing logos all come back `success`.
11. **Rewriting prompts for render noise.** A garbled hand from a correct prompt needs a REGENERATION, not a revision cycle. Classify the failure first (Section 10.1).
12. **Unbounded polling.** The 100-poll cap exists because a stuck task once meant an agent polling forever. Cap, checkpoint, escalate.
13. **Unbounded regeneration spend.** The 2x SLIDE_COUNT budget exists for the same reason. Warn at 1.5x, stop at 2x.
14. **Silent truncation.** If the API forces a prompt cut, front-load and LOG it.
15. **No checkpoints.** A crash without checkpoints means re-paying for the whole run.
16. **Mixing deck versions.** Fresh dated workdir and v<N> names, every run.
17. **Fabricating proof.** Testimonials, numbers, press: from the client or `[CLIENT TO SUPPLY]`. If still unfilled at assembly, restructure the slide; never invent.
18. **Claiming delivery without verifying.** Check every destination first.
19. **Running phases serially when parallel is possible.** Token furnace. See Section 12.
20. **Thin prompts.** "White background, headline centered, professional feel" produces a mediocre slide. Calibrate to the Section 7.5 exemplar: characterized background, thirds placement for every element, hair/clothing/expression for every person, font PLACEMENT not just typeface, drawn objects described, overlays stated.
21. **Skipping thirds language.** "Centered" is not a composition brief. Auto-fail.
22. **Unstated overlays.** Say "overlaid" or the model renders elements side-by-side or fused.
23. **Strikethrough as a font style.** Describe the strike as a DRAWN LINE through the numerals (Section 7.4) or it will not render; fall back to native PPTX text after two failures.
24. **Dense slides.** More than one idea, more than 3 text blocks, more than 6 stack rows: split the slide. gpt-image-2 garbles dense text every time.
25. **Misnamed files.** Local `slide-NN.png` kebab-case; GHL `Slide NN v<N>`. Mix them and python-pptx assembles in the wrong order.
26. **Asking questions the agent already knows the answer to.** Discovery is 3 to 10 questions, adaptive. Re-asking brand colors that are on file wastes the client's patience and the question budget.
27. **Stacking all the drops at the end.** The proven ladder SPREADS across the deck with a buildup before every drop. Drops dumped back-to-back in the close read as desperation, not reward.
28. **Numbers that drift between slides.** $5,282 on the stack slide, $5,276+ on the recap slide: it shipped. Cross-slide numeric consistency is now a copy QC auto-fail.
29. **No watchdog on a long run.** A stalled poll loop at 2am wastes the night. The resilience cron (11.5) resumes stalled stages from checkpoints every 10 minutes.
30. **Singing the hook once, at the end.** Nobody waits until the end of the song to sing Purple Rain. Seven-plus refrains, starting early, or the audience leaves remembering nothing.
31. **Dropping price by stripping value.** Every drop ADDS to the table. The lower the price, the greater the value.
32. **Over-teaching.** They got dinner instead of an appetizer, so they left full and bought nothing.
33. **Putting the script on the slide.** If the slide says what the presenter says, nobody listens; the slide carries the idea, the presenter carries the words.
34. **Bulleting four pains onto one slide.** Each pain gets its own slide and its own emotionally driven image, no matter what.
35. **Emojis in a premium deck.** Icons cheapen it instantly. Photography and typography only.
36. **Same text position every slide.** Eyes fade out. Move the anchor; keep them hunting.
37. **Skipping the echo.** An agent that cannot echo the mission and produce its own list of promises has not understood the job, and the run will prove it expensively.
38. **Dying silently.** Tokens ran out, a model went down, a loop stalled, and nobody said anything. Escalate immediately, every time.
39. **300 slides for a 3-hour talk.** The cap tapers. 90 is the absolute ceiling. One big idea per slide governs everything.

---

*End of SOP v2.0. If anything in a live run contradicts this document, stop, escalate to the operator, and do not improvise around a hard rule (model, rate cap, white base, verbatim copy, owner approval, poll cap, budget cap, thresholds).*

---

## APPENDIX A: KIE.AI GPT IMAGE 2 API QUICK REFERENCE (authoritative for Phase 4)

| Item | Value |
|---|---|
| Platform | Kie.ai (the pinned image platform for this SOP) |
| Text-to-image model string | `gpt-image-2-text-to-image` |
| Image-to-image model string | `gpt-image-2-image-to-image` |
| Create task | `POST https://api.kie.ai/api/v1/jobs/createTask` |
| Check task | `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>` |
| Auth | `Authorization: Bearer <CLIENT_KIE_API_KEY>` + `Content-Type: application/json` |
| Prompt ceiling | 20,000 characters in `input.prompt` (SOP authoring max: 15,000) |
| Reference images | `input.input_urls`, public https URLs, max 16 |
| Aspect ratios | auto, 1:1, 3:2, 2:3, 4:3, 3:4, 5:4, 4:5, **16:9**, 9:16, 2:1, 1:2, 3:1, 1:3, 21:9, 9:21 (this SOP pins 16:9) |
| Resolutions | 1K, 2K, 4K (this SOP pins 2K unless intake says otherwise) |
| Create response | `{ "code": 200, "data": { "taskId": "..." } }` |
| Task states | `waiting`, `success`, `fail` (treat fail/failed/error/cancelled as terminal) |
| Success payload | `data.resultJson` is a JSON STRING containing `{"resultUrls": ["https://..."]}`; download `resultUrls[0]` |
| Failure fields | `data.failCode`, `data.failMsg` (log both) |
| Optional | `callBackUrl` webhook on createTask (this SOP polls instead) |
| Cost benchmark | ~3 cents per image at 2K |

Rate cap, wave scheduling, polling cadence, and the 100-poll guard live in Section 9. If this appendix ever conflicts with live Kie.ai documentation, verify against the live docs, update the MODEL MANIFEST and this appendix with operator sign-off, and log the change.
