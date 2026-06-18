# How to Use the Presentations Department 🖼️

**Department:** Presentations
**Department head:** Director of Presentations
**Folder:** `departments/presentations/`
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> This is the plain-language guide to the Presentations department. Most
> people never realize this department exists or know how to put it to work.
> This document fixes that. When you ask "how do I use the Presentations
> department?", "how do I use the Brainstorming Buddy?", or "what does the
> Re-Pitch procedure do?", this is the document your agent reads to answer you.

---

## 1. What This Department Does (in plain language)

End-to-end branded webinar and slide-deck production: idea capture, source-to-deck
conversion, research and proof-gathering, hook development, offer/price ladder
choreography, copywriting, brand and typography systems, image-prompt authoring,
image generation, quality control at every phase, media-library hosting, PowerPoint
assembly, adversarial review, speaker guide + word-for-word script + audio demo,
live-presentation coaching, verified delivery, and department self-healing. It
coordinates with Marketing (deck brief), CRM (GHL media library), Research (proof
gaps), and the client's OpenClaw agent (discovery interview, approval gates, final
delivery).

**Canonical Render Module (mandatory for all producing roles):** All image
generation in this department MUST use the shared module at
`23-ai-workforce-blueprint/templates/presentation-render/render_deck.py`. Per-deck
renderers are FORBIDDEN (AF-RENDERER auto-fail). The canonical module validates
model sovereignty, prompt character floor, and structural block requirements before
any API call, and writes `render_manifest.json` to the workspace for QC.

In one sentence: **End-to-end branded webinar/slide decks: idea or source in →
researched, branded, QC'd deck + speaker guide + script + audio + verified delivery out.**

You do not need to know which specialist does what. You tell the department what you
want in plain English, and the department head (Director of Presentations) figures
out who handles it and routes it for you.

---

## 2. When to Use It

Reach for this department whenever you want any of the following:

- A branded webinar or sales deck built from a fuzzy idea ("I want a presentation about X").
- An existing video, audio, webpage, or report turned into a presentation.
- A standalone piece of a deck (just the hook, just the price ladder, just the speaker script, just an audio demo).
- A presentation researched and fact-checked before it goes out.
- A finished deck coached for live delivery, or packaged and delivered to a client.
- A first-time orientation to what this department can do.

If you are not sure whether a request belongs here, ask anyway. The department head
will either take it or hand it to the right team. You never have to get the routing
right yourself.

---

## 3. How to Ask It for Work

You have three ways to put this department to work. All of them are fine.

1. **Just say it in plain English.** Message your agent like a teammate:
   "I need a webinar deck for my coaching offer." That is enough to start.
2. **Name the department if you want to be specific.** "Have the Presentations
   department build me a sales deck." This routes straight to the Director of Presentations.
3. **Name a role if you know exactly who you want.** See Section 4 and ask by role:
   "Get the Hook Strategist to lock a hook for this deck."

A good request includes, where it applies: **what** you want, **who or what it is
for** (the audience), **when** you need it, and any **must-haves or limits** (offer,
price, brand, proof). You do not have to provide all of that. If something important
is missing, the department asks one or two quick questions before it starts rather
than guess. The brief is read back to you and locked only after you sign off.

---

## 4. The Roles Inside This Department

There are 24 roles. They fall into a natural order — intake, planning, research,
content, design, production, quality, packaging, and delivery — and work hands off
down that chain. You can ask the department as a whole (the Director routes for you)
or name any role directly.

### Intake & first contact

- **First-Time Onboarding (Nadia Wells)** — The once-per-user concierge that orients
  a newcomer to what the department does, who the roles are, and how to start.
  *Use it:* the very first time anyone touches the department, or on a "remind me how
  this works" request. It then hands you to the Brainstorming Buddy.

- **Brainstorming Buddy** — The first contact who turns a fuzzy "I want a
  presentation" idea into a locked, build-ready creative brief (capturing the six
  mandatory fields, including representation mix and grounded content, and the
  style-source choice). *Use it:* when you have an idea but no source material yet.
  Hands off to the Director once you sign off on the read-back brief.

- **Content-to-Presentation Architect** — The "turn THIS into a presentation" front
  door that ingests an existing source (video, audio, webpage, report) and extracts a
  build-ready brief plus the deliverable-bundle spec, deciding the audience mode.
  *Use it:* when you already have source material to convert (distinct from the
  idea-interview Buddy). Hands the source-derived brief to the Director.

### Planning & infrastructure

- **Director of Presentations** — The lead orchestrator who owns the entire deck
  pipeline end to end (discovery, slide architecture, team dispatch, quality gates,
  final delivery) without doing the hands-on work herself. *Use it:* as the central
  command for every deck run. She receives the locked brief and dispatches every
  specialist and gate below.

- **Capacity & Reliability Engineer** — The infrastructure specialist who runs the
  capacity probe + budget pre-flight (`capacity_plan.json`) and the resilience
  watchdog that self-heals stalled runs. *Use it:* before the Director dispatches any
  sub-agents (no dispatch until `capacity_plan.json` exists) and throughout image
  generation. It is the reason runs don't die silently; it escalates to the Healer.

### Research

- **Deep Research Specialist** — The mandatory pre-build researcher who verifies and
  materially improves every deck (competitor structures, pricing benchmarks,
  statistics, proof, grounded image context, objections, fact-validation, compliance)
  with cited sources. *Use it:* on EVERY deck run, immediately after brief lock and
  before the Hook Strategist. Its Research Brief feeds the Copywriter, Offer/Price,
  Typography, Image Creator, Hook, Devil's Advocate, and QC.

### Content (the words)

- **Hook Strategist** — Owner of the Hook Lab: generates, scores, field-tests, and
  has you select the single signature hook line, then maps it to exactly 3–4 dedicated
  pure-typography anchor slides. *Use it:* early in the copy phase to lock the hook.
  Outputs `hook_package.json` for the Slide Copywriter.

- **Offer & Price Strategist** — Owner of the spread value-ladder choreography (anchor
  + earned gradual drops + final below-ladder buy price) and the single source of
  truth for every pricing/value number. *Use it:* on any offer-bearing deck. Produces
  `price_ladder.json` that the Copywriter pulls from and QC validates against (the
  blocking gate for numeric consistency).

- **Slide Copywriter** — Authors every word on every slide (headlines, subheads,
  bullets, presenter notes), enforces one-big-idea-per-slide, runs the
  AUDIENCE-vs-SAY tagging pass, and never fabricates proof. *Use it:* to produce
  `slides_copy.md` for your approval before any image is generated. Consumes Hook,
  Offer/Price, and Research outputs.

### Design system (how it looks)

- **Brand Steward** — Creates and maintains the 800–1,500-character STYLE BLOCK
  (colors, typography law, logo placement, brand grammar, representation ratio) that
  travels with every image prompt and locks one canonical logo. *Use it:* as soon as
  the intake is complete, before any prompts are written. The Image Creator cannot
  write a single prompt without this STYLE BLOCK.

- **Typography Architect (Marcus Vane)** — Owner of the deck-wide design system
  (weight ladder, per-archetype type treatment, price-typography rules, per-slide
  archetype map) decided up front so the deck reads as one premium piece. *Use it:*
  after the Brand Steward locks the STYLE BLOCK and before the Image Creator writes
  prompts. Outputs `design_system.json`/`.md`.

### Production (the images)

- **Slide Image Creator** — Writes one complete 15-element image prompt per slide
  (declaring one of five archetypes, three engines on people-slides, paired negative
  block, typography law, gallery-grade standalone-art standard). *Use it:* after the
  STYLE BLOCK and design system are locked. Hands prompts to the Slide Submitter.

- **Slide Submitter** — The single detached agent that submits every prompt to Kie.ai
  (respecting the 20-requests/10-seconds cap), polls for completion, and downloads
  results to `working/renders/`. *Use it:* after prompts are written. It is the ONLY
  agent that touches the Kie.ai API, using the model the MODEL MANIFEST hardcodes.

### Quality (the gates)

- **QC Specialist** — The independent two-layer quality machine running every gate
  (copy, prompt, image, final deck): a hard auto-fail battery checked first, then an
  8.5-threshold / 7.0-floor average, looping back up to 3 times and escalating on the
  4th failure. *Use it:* at every quality gate — it is the last line between
  substandard work and your eyes.

- **Devil's Advocate** — The on-call adversarial reviewer who reads high-stakes deck
  copy as the most skeptical audience member and produces a scored Kill List against
  the 24-point Pitch Doctrine. *Use it:* on Director-flagged high-stakes decks (default:
  after copy QC, before your approval). HIGH-severity flags on fabricated proof or fake
  scarcity are BLOCKING gates, not suggestions.

### Packaging the artifacts

- **PPTX Assembly Specialist** — Assembles the final PowerPoint from QC-passed images
  (full-bleed 16:9 via python-pptx), embeds speaker notes, applies native text
  overlays, and exports BOTH a `.pptx` and a `.pdf`. *Use it:* as the last
  physical-artifact step after image QC passes. Both files must exist and pass the
  assembly gate before delivery.

- **Presenters Guide Specialist (Delia Crewe)** — Produces the speaker-facing OUTLINE:
  a beautiful PDF + Notion doc mapping slide-by-slide talking points and "land this"
  beats (font never below size 12). *Use it:* after copy is approved and presenter
  notes exist. This is the map of points to cover — distinct from the word-for-word script.

- **Presenters Speech Writer (Roland Pace)** — Writes the word-for-word webinar speech
  as four locked artifacts: clean speech `.md`, teleprompter `.pdf`/`.html`,
  Fish-tagged `.md`, and `PRESENTER-AUDIO.mp3`, in a passionate spoken delivery to a
  proven webinar arc. *Use it:* to produce the exact spoken words (the script, vs the
  Guide's map). Supplies the speaker-notes words and the audio source.

- **Fish Audio Expression Specialist** — Marks up the clean speech with Fish Audio
  expression tags (S2 `[bracket]` / S1 `(parenthesis)`, with ElevenLabs v3/v2
  translation) so emphasis, pauses, and emotional beats land in text-to-speech.
  *Use it:* to tag the script the audio render consumes. It adds tags only — never
  altering the words or running the render itself.

- **Audio Demonstration Specialist (Vivienne Locke)** — The Voice Director who turns
  the QC-passed speech into a marketable audio demo via the Expression Engine and a
  docs-grounded text-to-speech fallback chain (Fish Audio S2-Pro → ElevenLabs → Whisper
  verification). *Use it:* ONLY when the brief sets `WANT_AUDIO_DEMO = true`. Outputs
  the demo `.mp3` plus tagged script, and delivers through the Delivery Concierge.

### Delivery & live presentation

- **Media Librarian & GHL Updater** — Creates and maintains the local + GHL
  media-library folders at run start (Step 0) and uploads every QC-passed image to the
  client's GHL media library, verifying matching names and counts. *Use it:* at run
  start and after each image passes QC. It verifies media in both places before the
  PPTX Assembly Specialist begins, then hands the QC-passed PPTX to the Delivery Concierge.

- **Presenter Coach** — The Talk-Track Specialist who builds the timed slide-by-slide
  talk track, the Q&A objection prep, and the one-page rehearsal pack, and holds the
  Rehearsal Gate that marks a deck webinar-ready. *Use it:* in final position after the
  deck is assembled and QC-passed. The deck is not webinar-ready until you run it aloud
  to clear the gate.

- **Delivery Concierge** — Owner of the last mile: verifies every QC-passed deck
  reaches its verified destinations (local, GHL, Drive), notifies you with exact
  locations and QC score, and never makes an unverified "done" claim. *Use it:* as the
  final checkpoint before a run is called complete.

### Department self-care

- **Healer** — The department's immune system that diagnoses the root cause of any
  pipeline error, fixes the run, patches the SOP so the failure can never recur, and
  watches for model/version updates and SOP-coverage gaps under a strict three-tier
  authority system. *Use it:* on any error, bug, stall, or failure (it also receives
  Capacity/Reliability watchdog handoffs). It fixes within its own authority and holds
  bigger structural changes for your approval.

---

## 5. The Procedures (SOPs) Behind the Work

You never have to invoke a procedure by hand — the roles run them for you. This
section exists so that when you ask "what does X do?" your agent can answer precisely.
There are 47 procedures: 23 shared doctrine procedures plus one per-role procedure
file for each of the 24 roles.

### Doctrine procedures — Intelligence Engines

- **The Intelligence Engines Framework (SOP-ENGINE-00)** — The single map of the nine
  named INTELLIGENCE ENGINES this department runs against every deck — Facial, Lighting,
  Typography, Story, World, Pricing, Hook, Recap, and Product (roadmap) — each with a
  definition, a "how you know it landed" check, and named failure modes that auto-fail at
  QC. It promotes the three engines the image pipeline already ran by name (Facial,
  Audience, World) and the two pitch mechanics (Hook, Recap) into the full named set, and
  points each engine at its enforcement rather than duplicating it. *Use case:* the
  artifact your agent reads when you ask "what makes our slides different?" or "which
  engine owns X?"; the framework behind the per-engine auto-fails in SOP-SLIDE-00.

### Doctrine procedures — Casting

- **Audience Composition Intake & Casting Ledger (SOP-CAST-01)** — Makes your real
  audience composition the single source of truth for every people image, eliminating
  invented demographics. *Use case:* runs at intake on any deck with people-slides; it
  halts the build if audience composition isn't captured and builds the casting ledger
  QC tallies against.

### Doctrine procedures — Design system

- **Design Integration Map (SOP-DESIGN-00)** — The wiring record showing how the
  design-system overhaul lands in existing files and which QC codes already enforce its
  rules. *Use case:* consulted when wiring or auditing the design auto-fails; prevents
  duplicate rule namespaces.

- **Creative Typography Guide (SOP-DESIGN-01)** — Encodes the locked 4-weight ladder,
  expressive display rules, per-word emphasis, hierarchy, and the falling-price /
  rising-value type pairing. *Use case:* run by the Typography Architect to lock the
  type system; QC checks prompts and renders against it to fail "cookie-cutter" decks.

- **Pure-Typography Hook Slides (SOP-DESIGN-02)** — Defines the visual design of the
  3–4 dedicated hook slides (hook line large over a ≤15%-opacity image, no footer, no
  competing subject, verbatim refrain). *Use case:* applied when rendering hook anchors;
  kills footer-wallpaper / doubled / mutated-hook defects.

- **Variable Layout / Anti-Template (SOP-DESIGN-03)** — Turns the five-archetype system
  into an enforced rotation of image position and word-block placement so the deck reads
  cohesive but never cookie-cutter. *Use case:* run by the Typography Architect and at
  final QC, which auto-fails decks with too few archetypes or a repeated word stack.

- **Logo Consistency (SOP-DESIGN-04)** — Guarantees one canonical logo composited
  image-to-image at a fixed size and position on every slide, making logo drift or
  misspelling an auto-fail. *Use case:* used by the Brand Steward (lock the mark) and
  Image Creator (composite it); QC runs cross-slide logo-drift comparison.

### Doctrine procedures — Image generation mechanics

- **Image Cluster Index & Wiring (SOP-IMG-00)** — Index of the image-generation cluster
  and the exact edits that fold these procedures into the role files. *Use case:*
  reference when wiring the image SOPs into roles.

- **Kie.ai Call Mechanics (SOP-IMG-01)** — Gives the exact request/response/lifecycle
  for the three image modes (text-to-image, image-to-image, analysis), mandates the
  deterministic shipped-script render path and the English/Latin-only prompt pin, and
  defines the full prompt+image QC gate. *Use case:* followed by the Slide Submitter at
  submit time; forces image-to-image whenever a logo or portrait is in play.

- **Design-Intelligence-Library Integration & Seeding (SOP-IMG-02)** — Defines the
  seeding step that fills the design library and how Presentations consumes a named
  style family. *Use case:* fires inside the Brand Steward's procedure when the intake
  declares a style reference; analyzes a reference deck into named families.

- **Style-or-Creative-Develop Conversation (SOP-IMG-03)** — Adds the verbatim three-way
  style-source intake branch (match a reference / use a saved style / creatively
  develop one) plus the creative-develop micro-interview and the saved-styles seed file.
  *Use case:* asked by the Brainstorming Buddy on every new deck before the STYLE BLOCK
  is built.

- **Signature Style Recall + Logo Image-to-Image (SOP-IMG-04)** — Makes saved-style
  recall deterministic (alias → versioned style card → STYLE BLOCK, no guessing) and
  specifies the logo-as-image-to-image mechanic. *Use case:* runs when the style source
  is a saved style; shows the Lookbook rather than guessing on an unknown alias.

- **PIL Logo Composite + Native Text Overlay (SOP-IMG-05)** — Makes logo identity and
  hero-text rendering deterministic via code: a mandatory logo composite on every slide
  and a native-text overlay for hero strings, plus the gradient-on-type ban. *Use case:*
  run by the PPTX Assembly Specialist post-render to eliminate logo-drift and
  gradient-on-type defects before QC.

### Doctrine procedures — Pitch craft

- **Slow-Drop Pitch Process (SOP-PITCH-01)** — Makes the price drop a slow, earned
  reward: anchor planted early, beats spread out, a build-up before every drop, a new
  earned reason each time, escalating added value, and the falling-price / rising-value
  curve shown on screen. *Use case:* run by the Director (arc spacing) and Offer/Price
  Strategist (numbers); enforced at the gate.

- **Value Stack and Promises (SOP-PITCH-02)** — Requires promises planted before the
  anchor, every deliverable itemized with a value, a stack slide that exceeds the anchor
  before the cheapest price, escalating re-stacks, a value-gap slide before the final
  price, and a priceless frame for non-monetary offers. *Use case:* run by the
  Offer/Price Strategist and Copywriter; enforced by component-presence gates.

- **Re-Pitch / Mandatory Post-Price Recap (SOP-PITCH-03)** — Mandates a 4–7 slide recap
  block after the final price (full stack recap, value gap, promises, guarantee,
  objection kills, reset urgency, CTA, warm send-off) that restates and never introduces.
  *Use case:* run after the final price reveal; enforced by re-pitch presence and
  close-density gates.

- **Wall of Wins (SOP-PITCH-04)** — Makes the Wall of Wins a crowd of 4+ real
  named/located client results with an aggregate band and a "these are your peers" line,
  banning fabrication and the future-pace anti-pattern, placed ~5 slides before the
  offer. *Use case:* run by the Copywriter near the close; placeholders held until real
  wins arrive.

- **The Deliverable Bundle (SOP-PITCH-05)** — Guarantees every build produces three
  artifacts — Presenter Guide PDF, word-for-word script PDF, and a Fish-Audio rendition
  — and defines the exact 5-file client package and clean workspace structure. *Use
  case:* enforced at closeout (all three artifacts must be non-empty on disk) before any
  delivery action.

### Doctrine procedures — Slide craft

- **Master QC Auto-Fail Ruleset (SOP-SLIDE-00)** — The machine-checkable spine: the
  load-bearing ship-blocker auto-fails (hook ceiling / anti-footer, audience-facing-only,
  no rendered placeholder, hook integrity, one-big-idea) plus density auto-fails, with a
  map to the live fail codes and the QC check order. *Use case:* the reference QC runs in
  order at every gate so a deck cannot pass if it repeats known failures.

- **One Big Idea Per Slide (SOP-SLIDE-01)** — Makes "one core idea per slide" a hard gate
  with mandatory splits (diagnosis+method+outcome = 3 slides; value trio = 4; etc.), a
  3-text-block ceiling, and word ceilings. *Use case:* enforced at copy and render; the
  Director reserves the split slots at arc time.

- **Audience-Facing Only (SOP-SLIDE-02)** — Bans six categories from the slide face
  (speaker say-lines, internal pitch doctrine, image narration, meta-telegraphing
  including the word "webinar", credential dumps, rendered placeholder tokens) and routes
  each elsewhere. *Use case:* the Copywriter runs the AUDIENCE/SAY tagging pass; enforced
  at every QC gate.

- **Hook Doctrine / The Sacred Refrain (SOP-SLIDE-03)** — The verbatim hook appears on
  exactly 3–4 dedicated pure-type slides and nowhere else — never as a footer, never
  doubled / mutated / misspelled — with the signature quote kept a separate beat. *Use
  case:* owned by the Hook Strategist; enforced by the hook auto-fail battery.

- **Deck Density and Pacing (SOP-SLIDE-04)** — Adds hard minimum slide counts per
  section, the anchor-at-one-third rule, build-up-before-every-drop, mandatory stack /
  promises / Wall / re-pitch beats, and a minimum-gap floor between price beats. *Use
  case:* run by the Director as an arc-time density pre-check; enforced at the gate.

### Per-role procedures

Each of the 24 roles ships a procedure file mirroring the numbered steps in its role
definition (the role definition is authoritative). In order of the pipeline:

- **First-Time Onboarding** — Orients a brand-new client: first-time orientation, roles
  tour and surface explainer, hand-off to the Brainstorming Buddy (sets the seen flag),
  and on-demand refresher. *Use case:* the first time anyone engages the department, or
  a "remind me how this works" request.

- **Brainstorming Buddy** — The client intake interview: a short (≤7-question) or
  extensive (10–20-question) version, confirm-and-lock the brief, and kickoff/handoff —
  including the verbatim style-source branch. *Use case:* run first on a new deck request
  to capture the brief and set the style source.

- **Content-to-Presentation Architect** — Turns an existing source into a deck: audience-
  mode decision, source ingestion per modality (with a privacy rule), signal-vs-fluff,
  the analysis/hook/teaching arc, persuasion-intelligence extraction, teaching devices,
  micro-vs-full sizing, the deliverable bundle, handoff, and trigger phrases. *Use case:*
  run when the request is "turn this into a presentation."

- **Director of Presentations** — Orchestrates the whole build: brief ingest and
  validation, the echo protocol + mission gate, mode selection + enhancement-gap
  analysis, slide-count math + arc allocation, the owner approval gate + presenter-notes
  export, and parallelization/sequencing. *Use case:* run from kickoff through approval
  to plan the deck and dispatch specialists.

- **Capacity & Reliability Engineer** — Sizes the build and keeps it resilient: capacity
  probe + fleet sizing, the resilience watchdog cron + checkpoint recovery, and model
  routing + environment-store verification. *Use case:* run at the pre-flight step so the
  Director knows safe concurrency, render-credit budget, and model routing before
  dispatching agents.

- **Deep Research Specialist** — Mandatory pre-build research: niche / offer-benchmark /
  corroboration research (with an 8-URL citation floor), grounded image-context
  extraction, design/typography research, and deep validation + persuasion research.
  *Use case:* run on every deck to verify every stat, price, and claim and anchor the
  offer against market comps before copy is written.

- **Hook Strategist** — Generates and places the hook: hook generation + scoring (Hook
  Lab part 1), then the variant ladder + placement map + post-deck hook audit. *Use case:*
  run early to lock the canonical hook string, name the 3–4 anchors, and produce the
  hook-absent list QC checks.

- **Offer & Price Strategist** — Builds the offer economics: the spread value-ladder
  choreography, offer stack + value anchor, cross-slide numeric consistency / price
  validation, the straight one-reveal and VIP two-option close variants, the
  priceless/cost-vs-value frame, the expertise-over-charisma ascension ladder, guarantee
  + scarcity, and the re-pitch choreography. *Use case:* run at copy stage to produce the
  ladder numbers, escalating value adds, running total, and re-pitch that the pitch
  procedures enforce.

- **Slide Copywriter** — Writes the slide words: words-first / one-big-idea drafting,
  hook placement on dedicated slides as a ceiling, the proof-integrity / no-fabrication
  gate, Mode-B word-preserving augmentation, the doctrine-application checklist, and the
  AUDIENCE/SAY tagging pass. *Use case:* run at the copy phase to produce `slides_copy.md`
  and the audience/say tags QC requires.

- **Brand Steward** — Authors and enforces the shared STYLE BLOCK: STYLE BLOCK authorship
  (including locking one logo and the style-source trigger), cross-slide consistency +
  representation-ratio audit, archetype palette/exemplar handoff, and the typography law.
  *Use case:* run alongside copy, completing before the image phase so every prompt
  inherits one locked brand system.

- **Typography Architect** — Locks the deck's type and layout before prompts exist:
  weight ladder + type token system, the five-archetype layout rotation plan, the full
  price-typography ladder, and the per-slide type plan + anti-cookie-cutter audit. *Use
  case:* run after the STYLE BLOCK to produce the type system, layout map, and treatment
  table the Image Creator and QC consume.

- **Slide Image Creator** — Authors every image prompt: the 15-element prompt spec, the
  five archetypes + thirds grid + expression vocabulary, white-base/palette + lighting
  library, people/overlays/logo + density calibration, drawn-strikethrough handling,
  designed-typography enforcement, color theory/grading, the mandatory paired
  negative-prompt block, a concrete full-prompt template, and the vision-gate producing
  rules. *Use case:* run at the image phase to write QC-passable, image-to-image,
  treatment-table-driven prompts.

- **Slide Submitter** — Submits prompts to Kie.ai and retrieves renders: model manifest +
  variant selection, submit + the 20/10-second rate cap, loop-guarded poll + parallel
  download, the authoritative API contract, truncation / generation-budget discipline,
  and an API smoke test. *Use case:* run at the submit phase to choose the correct mode,
  submit within limits, poll safely, and download each render.

- **QC Specialist** — The full quality gate: copy QC, prompt QC (dual-scored), image QC +
  fail classification, the revision-loop control + escalation, final-deck QC with
  composed-slide assertions, and the delivery interlock. *Use case:* run at every phase —
  it owns all the auto-fail codes the doctrine procedures define and blocks final status
  until the final deck QC passes.

- **Devil's Advocate** — Adversarial doctrine review producing a kill-list of weak or
  risky pitch and design choices. *Use case:* run on-call when a deck needs a red-team
  pass before it ships.

- **PPTX Assembly Specialist** — Assembles and exports the final deck: the PowerPoint
  build with embedded speaker notes, export to PDF + final QC, the native-text overlay
  fallback, and the typography-safe assembler spec. *Use case:* run at the assembly phase
  to composite native logo/text overlays, build the `.pptx`, and export the `.pdf`.

- **Media Librarian & GHL Updater** — Manages all media assets and their hosting: Step-0
  landing-zone creation, passed-image intake, gated GHL/Drive upload, delivery + ground-
  truth verification, client asset acquisition, and final deck delivery. *Use case:* run
  at run start and through render to host the logo/assets at public URLs and archive
  QC-passed images.

- **Presenters Guide Specialist** — Builds the presenter-facing guide: the speaker
  outline, a beautiful PDF (font ≥12), a published Notion doc, and the surface-boundary
  audit + delivery. *Use case:* run during closeout to produce the Presenter Guide PDF the
  deliverable bundle requires.

- **Presenters Speech Writer** — Writes the spoken deliverable: the word-for-word webinar
  speech (~130 words per minute), the teleprompter PDF/HTML/Notion, the Fish-tagged
  deliverable, the audio demo via the text-to-speech fallback chain, and the surface-
  boundary audit + delivery. *Use case:* run after copy is approved to produce the script
  PDF (and feed the audio render) required at closeout.

- **Fish Audio Expression Specialist** — Expression-tagging discipline across text-to-
  speech tiers: tag for the target tier, the word-fidelity + tag-discipline audit, and
  cross-tier translation guidance. *Use case:* run to tag a script for the chosen tier and
  verify the tags don't alter the words.

- **Audio Demonstration Specialist** — Turns the approved speech into a directed,
  verified audio demo: expression tagging, chunk + synthesize with the fallback chain,
  the ffmpeg stitch + loudness normalize, speech-to-text verification, and deliver the
  mp3. *Use case:* run when an audio demo is wanted, after the speech passes QC, to
  produce a verified narration track.

- **Presenter Coach** — Prepares the presenter to deliver: the talk track, the Q&A
  objection prep, the rehearsal pack, and the rehearsal gate. *Use case:* run after the
  deck and script are final to coach delivery and gate readiness.

- **Delivery Concierge** — Packages and delivers the final bundle: package assembly +
  hygiene sweep, destination resolution, multi-destination upload, notification, and
  ground-truth verification. *Use case:* run at closeout to assemble the clean 5-file
  package, upload it, notify you, and verify on disk before declaring delivery done.

- **Healer** — Incident diagnosis and permanent repair of the department itself: intake /
  triage, five-whys root cause, hot patch, SOP surgery, gap / new-procedure drafting,
  model-currency census, the healing report, regression watch, core-file surgery,
  settings/JSON repair, teach-self, and embedding/index refresh. *Use case:* run on a QC-
  loop escalation or any department failure to fix forward and guarantee the defect never
  recurs.

---

## 6. What to Expect Back

When you ask this department for something, here is the normal flow:

1. **Acknowledgment.** The Director of Presentations confirms the request landed and, if
   anything important is unclear, asks one or two quick questions, then reads the brief
   back to you for sign-off.
2. **Routing.** The work is matched to the right role(s) and procedure. Nobody guesses;
   if there is no procedure for your request, the Healer writes one before work starts.
3. **The work itself.** The roles do the job in pipeline order, checked by QC (and the
   Devil's Advocate on high-stakes decks) at every gate before it reaches you.
4. **Delivery.** You get the finished deck plus its bundle (Presenter Guide, word-for-word
   script, and — if requested — an audio demo). The Delivery Concierge confirms exact
   locations and the QC score. Anything needing your sign-off is flagged first.

Typical turnaround depends on the size of the request. A standalone piece (a hook, a
price ladder, a script) comes back the same working session; a full deck comes back with
a clear estimate up front and a capacity/budget plan behind it.

---

## 7. How It Hands Off (to you and to other departments)

- **To you:** finished deliverables arrive in your workspace and you are notified.
  Anything marked owner-approval-required waits for your yes before it ships, and the
  deck is not "webinar-ready" until you clear the Presenter Coach's rehearsal gate.
- **To other departments:** when your request needs another team, this department
  coordinates the handoff through the company's routing map (`universal-sops/00-ROUTING.md`).
  You do not have to manage the handoff.
- **Escalation:** if something is blocked, needs a decision only you can make, or needs a
  credential or payment, it is escalated to you directly rather than stalling silently.

---

## 8. Quick Questions You Can Ask

You can ask your agent any of these at any time and it will answer from this document:

- "How do I use the Presentations department?"
- "What can the Presentations department do for me?"
- "How do I use the Brainstorming Buddy / Hook Strategist / Audio Demonstration Specialist?"
- "What does the Re-Pitch procedure (or the Wall of Wins, or One Big Idea Per Slide) do?"
- "Who turns an existing video into a presentation?"
- "What do I get back if I ask Presentations for a webinar deck?"

---

*This guide is generated for {{COMPANY_NAME}} by the AI Workforce Blueprint
(Skill 23). It is regenerated whenever the department's roster changes so it always
matches the roles and procedures you actually have.*
