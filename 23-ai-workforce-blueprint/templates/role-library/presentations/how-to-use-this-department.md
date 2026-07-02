# How to Use the Presentations Department 🖼️

**Department:** Presentations
**Department head:** Director of Presentations
**Folder:** `departments/presentations/`
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> This is the plain-language guide to the Presentations department. Most
> people never realize this department exists or know how to put it to work.
> This document fixes that. When you ask "how do I use the Presentations
> department?" or "how do I use the Audio Demonstration Specialist?", this is the
> document your agent reads to answer you.

---

## 1. What This Department Does (in plain language)

End-to-end branded webinar and slide deck production: copy writing, price ladder choreography, image prompt authoring, brand consistency, QC at every phase, image generation submission, media library management, PPTX assembly, adversarial review, hook development, live-presentation coaching, verified delivery, and department self-healing. Coordinates with Marketing (deck brief), CRM (GHL media library), Research (proof gaps), and the client's OpenClaw agent (discovery interview, approval gates, final delivery). **Canonical Render Module (mandatory for all producing roles):** All image generation in this department MUST use the shared module at `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py`. Per-deck renderers are FORBIDDEN (AF-RENDERER auto-fail). The canonical module validates model sovereignty, prompt character floor, and structural block requirements before any API call, and writes the render record to `working/checkpoints/process_manifest.json` (via `write_process_manifest`) for QC verification. The older `templates/presentation-render/render_deck.py` + `render_manifest.json` path is RETIRED - its checks were folded into `build_deck.py` and nothing imports it; see `docs/LEGACY-RETIREMENT.md`. **The Intelligence Engines (the department's named capability set):** Every deck is run against NINE named INTELLIGENCE ENGINES  -  Facial, Lighting, Typography, Story, World, Pricing, Hook, Recap, and Product (roadmap)  -  each defined with a verification check and auto-failed failure modes in `sops/SOP-ENGINE-00-INTELLIGENCE-ENGINES-FRAMEWORK.md`. The framework promotes the three engines the image pipeline already ran by name (Facial, Audience, World) and the two pitch mechanics (Hook, Recap) into the full set, and wires each engine to its enforcement (SOP-SLIDE-00 Section 8).

In one sentence: **End-to-end branded webinar/slide decks: copy, price ladder, images, QC, delivery**

You do not need to know which specialist does what. You just tell the department
what you want in plain English, and the department head (Director of Presentations)
figures out who handles it and routes it for you.

---

## 2. When to Use It

Reach for this department when you want any of the following:

- **Build my Trevor Otts Signature Presentation** -- the 4-phase, >= 100-slide signature talk (Avatar -> Signature Story -> Transformational Teaching -> Purpose Pitch) with your choice of The Rulebook / The Vault / The Quest / The Original frame (Skill 51). See "Requesting a Signature Presentation" in Section 3.
- Turns the QC-passed Presenters Speech into a marketable AUDIO DEMO.
- Creates and owns the STYLE BLOCK (800-1,500 characters).
- Capacity and Reliability Engineer for the company, the specialist responsible for ensuring every deck run.
- The front door for one specific request.
- Owns Phase 6+ multi-destination deck delivery.
- The first time (or anyone on their team) touches this department, you are the welcome.

If you are not sure whether a request belongs here, ask anyway. The department
head will either take it or hand it to the right department. You never have to
get the routing right yourself.

---

## 3. How to Ask It for Work

You have three ways to put this department to work. All of them are fine.

1. **Just say it in plain English.** Message your agent like you would a
   teammate: "I need help with something from the presentations team." That is enough to start.
2. **Name the department if you want to be specific.** "Have the
   Presentations department handle something from the presentations team." This routes
   it straight to Director of Presentations.
3. **Name a specialist if you know exactly who you want.** See the specialist
   list in Section 4 and ask for them by role: "Get the Audio Demonstration Specialist
   to take on a presentations task for you."

A good request includes, where it applies: **what** you want, **who or what it
is for**, **when you need it**, and any **must-haves or limits**. You do not have
to provide all of that. If something important is missing, the department will
ask you one or two quick questions before it starts rather than guess.

### Requesting a Signature Presentation (the Trevor Otts 4-phase signature talk, Skill 51)

If you want the **Signature Presentation** deck type -- the Trevor Otts methodology, not the standard webinar deck -- just say so ("build my signature presentation" / "I want a signature talk"). Here is how it runs:

- **You are asked one branch question up front:** standard webinar deck, or a **Signature Presentation**? Choose the Signature Presentation and the department switches on the SACRED 4-phase build (`deck_type: signature_presentation`), owned by the Signature Presentation Architect.
- **The 8 Questions, asked all at once.** Instead of one-question-at-a-time, the Signature Presentation Architect (via the Brainstorming Buddy) sends you the eight sacred questions in ONE message block -- title, alternate titles, avatar pain points, story elements, teaching topic ("7 Secrets to ___", "The ___ Blueprint..."), alternate teaching titles, the product(s) you offer at the end, and anything else. Answer them together; nothing is written until they are all answered.
- **You pick a frame** (asked in that same block) -- the frame governs HOW your Transformational Teaching is taught:
  - **The Rulebook** -- numbered, non-negotiable Rules, each with an affirmation and a 3-step action plan, capped with a recap and a teased bonus Rule.
  - **The Vault** -- numbered Secrets unlocked one at a time, each paired with a famous quote and its own affirmation, tied together by one running metaphor.
  - **The Quest** -- a named Blueprint organized as Quests with steps and affirmations, closing on a poetic manifesto you finish in your own words.
  - **The Original** -- a from-scratch frame designed around your own methodology.
  (Not sure? Say "show me" and you'll get your teaching topic sketched in the frames, one line each, before you pick.)
- **Length: >= 100 slides by default.** The signature arc runs Avatar (>= 11) -> Signature Story (>= 13) -> Transformational Teaching (>= 36, taught in 3-7 steps, with NO pitching) -> Purpose Pitch (>= 40), for 100+ slides total. **If you ask for an EXACT slide count, your number wins** -- the exact count is honored precisely and the deviation is logged on the process certificate; otherwise the 100-slide floor governs.
- Everything else -- the visual style branch, the 3-variant style preview, image generation, PPTX assembly, speech/guide/audio, and verified delivery -- runs exactly as it does for any deck in this department. When the deck reaches QC, the independent QC Specialist (Signature Presentations) grades it against the SACRED law before it can be delivered.

---

## 4. The Specialists Inside This Department

Each specialist below is built for one job. You can ask the department as a whole
and it will pick the right one, or you can ask for a specialist by name.

| Specialist | What it is for |
| --- | --- |
| **Audio Demonstration Specialist** | Turns the QC-passed Presenters Speech into a marketable AUDIO DEMO. |
| **Brand Steward** | Creates and owns the STYLE BLOCK (800-1,500 characters). |
| **Capacity Reliability Engineer** | Capacity and Reliability Engineer for the company, the specialist responsible for ensuring every deck run has. |
| **Content To Presentation Architect** | The front door for one specific request. |
| **Delivery Concierge** | Owns Phase 6+ multi-destination deck delivery. |
| **First Time Onboarding Presentations** | The first time (or anyone on their team) touches this department, you are the welcome. |
| **Fish Audio / Expression Specialist** | Makes the audio demonstration of the Presenter's Speech sound like a real. |
| **Hook Strategist** | Owns the Hook Lab end-to-end. |
| **Media Librarian GHL Updater** | Media Librarian and GHL Updater for the company, the specialist responsible for two critical tasks in the CLIENT. |
| **Offer Price Strategist** | Offer and Price Strategist for the company, the specialist who owns the single highest-stakes choreography in any. |
| **Pptx Assembly Specialist** | Assembles the final PowerPoint from QC-passed images using python-pptx (13.333 x 7.5 inch slides, full-bleed). |
| **Presenter Coach** | Owns the live-presentation preparation layer. |
| **Presenters Guide Specialist** | Converts the QC-passed deck + the Presenter Coach talk track into a beautiful speaker-facing OUTLINE (one block per. |
| **Presenters Speech Writer** | Writes the FULL word-for-word "here is what you say" script keyed to each slide. |
| **Slide Copywriter** | Writes every word on every slide (Phase 1). |
| **Slide Image Creator** | Writes one 15-element image prompt per slide (Phase 2). |
| **Slide Submitter** | Submits all prompts to Kie.ai GPT Image 2 (Phase 4). |
| **Typography Architect** | Runs as a Phase-0.7/1.5 gate AFTER the Brand Steward emits the STYLE BLOCK and the Director emits arc_allocation.json. |
| **Prompt Author** | You write each slide's rich image prompt to the 9,000-to-18,000-character density standard (hard floor 9,000. |
| **Attention Content Strategist** | Attention Content Strategist for  -  the Priority-Shift Architect and Content Provocateur. |
| **Signature Presentation Architect** | Owns the Trevor Otts Signature Presentation deck type end to end -- the SACRED 4-phase, >= 100-slide methodology, the 8-Questions intake, and the frame selection (Skill 51). |
| **QC Specialist (Signature Presentations)** | The independent grader for a Signature Presentation -- runs the AF-SP-* auto-fail battery and the 8.5 semantic score, never self-grades (Skill 51). |

### What each specialist is for, with an example request

**Audio Demonstration Specialist**

- *What it is for:* Turns the QC-passed Presenters Speech into a marketable AUDIO DEMO.
- *Example request:* "Have the Audio Demonstration Specialist take this on: Turns the QC-passed Presenters Speech into a marketable AUDIO DEMO."

**Brand Steward**

- *What it is for:* Creates and owns the STYLE BLOCK (800-1,500 characters).
- *Example request:* "Have the Brand Steward take this on: Creates and owns the STYLE BLOCK (800-1,500 characters)."

**Capacity Reliability Engineer**

- *What it is for:* Capacity and Reliability Engineer for the company, the specialist responsible for ensuring every deck run has.
- *Example request:* "Have the Capacity Reliability Engineer take this on: Capacity and Reliability Engineer for the company."

**Content To Presentation Architect**

- *What it is for:* The front door for one specific request.
- *Example request:* "Have the Content To Presentation Architect take this on: The front door for one specific request."

**Delivery Concierge**

- *What it is for:* Owns Phase 6+ multi-destination deck delivery.
- *Example request:* "Have the Delivery Concierge take this on: Owns Phase 6+ multi-destination deck delivery."

**First Time Onboarding Presentations**

- *What it is for:* The first time (or anyone on their team) touches this department, you are the welcome.
- *Example request:* "Have the First Time Onboarding Presentations take this on: The first time (or anyone on their team) touches this department, you are the welcome."

**Fish Audio / Expression Specialist**

- *What it is for:* Makes the audio demonstration of the Presenter's Speech sound like a real.
- *Example request:* "Have the Fish Audio / Expression Specialist take this on: Makes the audio demonstration of the Presenter's Speech sound like a real."

**Hook Strategist**

- *What it is for:* Owns the Hook Lab end-to-end.
- *Example request:* "Have the Hook Strategist take this on: Owns the Hook Lab end-to-end."

**Media Librarian GHL Updater**

- *What it is for:* Media Librarian and GHL Updater for the company, the specialist responsible for two critical tasks in the CLIENT.
- *Example request:* "Have the Media Librarian GHL Updater take this on: Media Librarian and GHL Updater for the company."

**Offer Price Strategist**

- *What it is for:* Offer and Price Strategist for the company, the specialist who owns the single highest-stakes choreography in any.
- *Example request:* "Have the Offer Price Strategist take this on: Offer and Price Strategist for the company, the specialist who owns the single."

**Pptx Assembly Specialist**

- *What it is for:* Assembles the final PowerPoint from QC-passed images using python-pptx (13.333 x 7.5 inch slides, full-bleed).
- *Example request:* "Have the Pptx Assembly Specialist take this on: Assembles the final PowerPoint from QC-passed images using python-pptx (13.333 x 7.5."

**Presenter Coach**

- *What it is for:* Owns the live-presentation preparation layer.
- *Example request:* "Have the Presenter Coach take this on: Owns the live-presentation preparation layer."

**Presenters Guide Specialist**

- *What it is for:* Converts the QC-passed deck + the Presenter Coach talk track into a beautiful speaker-facing OUTLINE (one block per.
- *Example request:* "Have the Presenters Guide Specialist take this on: Converts the QC-passed deck + the Presenter Coach talk track into a beautiful."

**Presenters Speech Writer**

- *What it is for:* Writes the FULL word-for-word "here is what you say" script keyed to each slide.
- *Example request:* "Have the Presenters Speech Writer take this on: Writes the FULL word-for-word "here is what you say" script keyed to each slide."

**Slide Copywriter**

- *What it is for:* Writes every word on every slide (Phase 1).
- *Example request:* "Have the Slide Copywriter take this on: Writes every word on every slide (Phase 1)."

**Slide Image Creator**

- *What it is for:* Writes one 15-element image prompt per slide (Phase 2).
- *Example request:* "Have the Slide Image Creator take this on: Writes one 15-element image prompt per slide (Phase 2)."

**Slide Submitter**

- *What it is for:* Submits all prompts to Kie.ai GPT Image 2 (Phase 4).
- *Example request:* "Have the Slide Submitter take this on: Submits all prompts to Kie.ai GPT Image 2 (Phase 4)."

**Typography Architect**

- *What it is for:* Runs as a Phase-0.7/1.5 gate AFTER the Brand Steward emits the STYLE BLOCK and the Director emits arc_allocation.json.
- *Example request:* "Have the Typography Architect take this on: Runs as a Phase-0.7/1.5 gate AFTER the Brand Steward emits the STYLE BLOCK."

**Prompt Author**

- *What it is for:* You write each slide's rich image prompt to the 9,000-to-18,000-character density standard (hard floor 9,000.
- *Example request:* "Have the Prompt Author take this on: You write each slide's rich image prompt."

**Attention Content Strategist**

- *What it is for:* Attention Content Strategist for  -  the Priority-Shift Architect and Content Provocateur.
- *Example request:* "Have the Attention Content Strategist take this on: Attention Content Strategist for  -  the Priority-Shift Architect and Content Provocateur."

**Signature Presentation Architect**

- *What it is for:* Owns the Trevor Otts Signature Presentation deck type end to end -- the SACRED 4-phase, >= 100-slide methodology (Avatar -> Signature Story -> Transformational Teaching -> Purpose Pitch), the 8-Questions-in-one-block intake, and the frame selection (The Rulebook / The Vault / The Quest / The Original).
- *Example request:* "Have the Signature Presentation Architect build my signature talk -- the 4-phase, 100-slide Trevor Otts presentation in The Quest frame."

**QC Specialist (Signature Presentations)**

- *What it is for:* The independent quality-control grader for a Signature Presentation -- runs the AF-SP-* auto-fail battery plus the 8.5 semantic score (frame fidelity, no-pitch-in-Phase-3, Movement+Message+Methodology), and never grades its own or the producer's work.
- *Example request:* "Have the QC Specialist (Signature Presentations) grade this signature deck before delivery."


---

## 5. What to Expect Back

When you ask this department for something, here is the normal flow:

1. **Acknowledgment.** Director of Presentations confirms the request landed and, if
   anything important is unclear, asks you one or two quick questions.
2. **Routing.** The work is matched to the right specialist and the relevant
   procedure (its SOP). Nobody guesses; if there is no procedure for your
   request, one is written before the work starts.
3. **The work itself.** The specialist does the job and it is checked by the
   department's quality-control review before it reaches you.
4. **Delivery.** You get the finished result: the finished presentations work you asked for.
   Anything that needs your sign-off before it goes live is flagged for your
   approval first.

Typical turnaround depends on the size of the request. Quick items come back the
same working session; larger projects come back with a clear estimate up front.

---

## 6. How It Hands Off (to you and to other departments)

- **To you:** finished deliverables arrive in your workspace and you are notified.
  Anything marked owner-approval-required waits for your yes before it ships.
- **To other departments:** when your request needs another team, this department
  coordinates the handoff for you through the company's routing map
  (`universal-sops/00-ROUTING.md`). You do not have to manage the handoff.
  
- **Escalation:** if something is blocked, needs a decision only you can make, or
  needs a credential or payment, it is escalated to you directly rather than
  stalling silently.

---

## 7. Quick Questions You Can Ask

You can ask your agent any of these at any time and it will answer from this
document:

- "How do I use the Presentations department?"
- "What can the Presentations department do for me?"
- "How do I use the Audio Demonstration Specialist?"
- "Who handles something from the presentations team?"
- "What do I get back if I ask Presentations for something from the presentations team?"

---

*This guide is generated for {{COMPANY_NAME}} by the AI Workforce Blueprint
(Skill 23). It is regenerated whenever the department's roster changes so it
always matches the specialists you actually have.*

---

## Canonical Entry Command (the only way to build a deck)

A deck is built by running, and ONLY by running, the single sanctioned entry script:

```
23-ai-workforce-blueprint/scripts/presentation-canonical-entry.sh   --run-dir <RUN_DIR> --slides slides.json --out <OUT>.pptx
```

That entry script runs three fail-closed gates before dispatching the canonical orchestrator (`run_signature_deck.py` -> `build_deck.py`):

1. **Deps check** - all required runtime dependencies are present.
2. **Bypass-scan** - refuses to start if any hand-rolled renderer or assembler exists in the run directory. Specifically: any non-canonical `*.py` defining a 2048x1152 `Image.new` slide canvas (AF-LOCAL-CANVAS), a native `add_textbox`/`add_text_box` overlay (AF-CANONICAL-RENDER-BYPASS), or a direct kie `createTask` call outside `build_deck.py` (AF-CANONICAL-RENDER-BYPASS).
3. **Version/hash pin** - the deployed renderer must be in lockstep with the SOP/manifest stack and match the pinned governed head.

**`python3 working/*.py` (writing and running your own per-deck driver/submit/assemble scripts) is the ungoverned path and is FORBIDDEN (AF-CANONICAL-RENDER-BYPASS).**

A gate may be skipped ONLY by an explicit, logged owner/founder approval token recorded in `working/checkpoints/process_manifest.json` (`owner_skip_approval`: `approved:true` + `approved_by` + `reason`, naming the exact gate code). Agents may NEVER skip a gate silently or by their own choice.

---

## AF-CANONICAL-RENDER-BYPASS - No Hand-Rolled Renderer (AUTO-FAIL)

All image generation MUST route through the canonical module `build_deck.py`. A hand-rolled per-deck assembler or renderer is FORBIDDEN. Specifically, the presence of `add_textbox` / `add_text_box` calls or a direct kie `createTask` call outside `build_deck.py` in any run-directory `*.py` file triggers AF-CANONICAL-RENDER-BYPASS. This auto-fail also fires when the entry check detects an attempt to bypass the sanctioned entry script.

---

## AF-LOCAL-CANVAS - No Local Canvas Fabrication (AUTO-FAIL)

A slide image MUST be generated via kie.ai GPT Image 2. A slide image fabricated locally (e.g. `canvas = Image.new('RGB', (2048, 1152), ...)`) is FORBIDDEN. The presence of a 2048x1152 `Image.new` call in any run-directory `*.py` file triggers AF-LOCAL-CANVAS.

---

## AF-IMAGE-QC-VISION - Real Pixel Image QC Required (AUTO-FAIL)

The image-QC pass is NOT satisfied by a JSON score alone. The QC report at `working/qc/image_qc_report.json` MUST declare a `vision_model` (the AI model that performed the pixel/vision read) and a `slides` list with at least one per-slide entry containing `baked: true`. A QC report that lacks the `vision_model` field or an empty `slides` list triggers AF-IMAGE-QC-VISION.

---

## AF-DARK-SLIDE - No Dark Slides (AUTO-FAIL)

Slides MUST use LIGHT / bright backgrounds by DEFAULT. DARK or black-background slides are NOT ALLOWED unless the CLIENT EXPLICITLY requests a dark theme via the intake flag `client_dark_theme: true`. Light is the default; dark is opt-in by client request only.

- DEFAULT: Light / bright background slides
- ALLOWED dark: Only when `client_dark_theme: true` is set in working/copy/intake.json
- AUTO-FAIL: Any dark/black/near-black default background without `client_dark_theme: true`

**To enable a dark theme:** during onboarding, explicitly tell the Director of Presentations you want dark slides. The Director will record `client_dark_theme: true` in your intake.json. Without this explicit request, all slides default to light/bright backgrounds and any dark background specification is an AUTO-FAIL blocked by the build pipeline.
