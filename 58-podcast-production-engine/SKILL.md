---
name: podcast-production-engine
description: Turn ONE completed podcast intake survey into ONE published podcast episode, end to end, autonomously, on the client's own box, with the client's own credentials, at a bounded cost, with independent quality control, full durability, and a client-facing dashboard. Fuses the fleet's render lane (Skill 57 podcast mode script writer plus Kie.ai cover, Skill 35 Fish render script plus Podbean playbook, Skill 30 Fish Audio reference) with the Skill 23 professional-podcast doctrine (director-of-podcast, podcast-host, audio-post-producer, qc-specialist-podcast, loudness mastering, quality gates). Runs the canonical 18-step pipeline across four output-type presets (Interview, Solo, Season-Strategy, Episode Asset Pack) and two production modes (Personal Podcast, Interview Style). Content work routes to Ollama Cloud Kimi 2.6 then GLM 5.2 then OpenRouter equivalents then Gemini 3.1 Flash Lite, NEVER an Anthropic model at runtime. The Convert and Flow data plane is Skill 44 caf plus Skill 29 REST only, never a Model Context Protocol tier inside the pipeline. Fish Audio synthesis uses model s2.1-pro via header with the client's own reference_id, never the free tier for client content. Two separate quality gates that are never conflated: the 8.5 ten-category build gate that decides whether work merges, and the 16 Tier-1 plus 10-dimension rubric plus 3-strike episode gate that decides whether an episode ships to a listener. Move in silence: the engine enrolls the workflow and STOPS, Convert and Flow owns every customer message. Zero em dashes, no triple backtick fences in any produced output.
version: 0.1.11
---

# Podcast Production Engine (Skill 58)

The canonical, per-client engine that turns one intake survey submission into one published
podcast episode, autonomously, on the client's own OpenClaw box, with the client's own
credentials, at a bounded cost, with independent quality control, durable state, and a
client-facing dashboard. This is the productionized, hardened FUSION of two mature fleet
lanes; it is INTEGRATION plus HARDENING of assets the fleet already owns, not a from-scratch
build, and reuse fidelity is a scored requirement of the build gate.

The fusion, stated once:

- The render lane knows how to WRITE and RENDER: Skill 57 podcast mode (script-writer prompt,
  Kie.ai cover prompt, deterministic quality provers, golden fixture), Skill 35's production
  Fish Audio render script, Skill 30's Fish Audio reference and voice standard operating
  procedure.
- The doctrine lane knows how to RUN A PROFESSIONAL PODCAST OPERATION: Skill 23
  role-library/podcast/ (director-of-podcast, podcast-host, audio-post-producer,
  qc-specialist-podcast) and role-library/audio/ (podcast-editor, podcast-producer,
  mastering), with loudness mastering at minus 14 to minus 16 LUFS integrated, four quality
  gates, guest handling, distribution, and key performance indicators.

The engine binds the render lane to the doctrine lane through the four output-type presets in
Section 8 so one skill serves both a solo founder recording a weekly personal episode in a
cloned voice and an interview-style lead generation machine built on the SHUA principle (Seen,
Heard, Understood, Acknowledged).

## The silence doctrine and the responsibility boundary (binding)

Move in silence. These are non-negotiable and every code path in this skill honors them:

1. ZERO client-facing messages from the engine. The engine sends no SMS, no email, no chat,
   no Telegram, nothing to the customer or the guest, ever. The engine enrolls the workflow
   and STOPS at the boundary. Convert and Flow owns every customer message. A delivery report
   goes to the OPERATOR channel only, never inside the script, never to the customer.
2. OPERATOR-VERBOSE, CLIENT-SILENT. Founder and operator surfaces are rich; customer-facing
   surfaces are silent. Owner alerts are suppressed during maintenance. Never run
   qc-completeness.sh standalone from this engine (it leaks a client Telegram alert).
3. NEVER print, echo, grep, or paste a secret value. Credentials are documented by label and
   location only. A credential check reports SET or NOT SET plus a behavior probe, never the
   value.
4. NEVER commingle clients. Only the named client's OWN accounts and keys are ever used. No
   operator, shared, agency, or other-client credential ever substitutes for a client's own.
   Per-client isolation is structural (physical box separation plus tenant check plus private
   integration token fingerprint plus per-client secrets), not policed after the fact.
5. CONFIG WRITES RUN AS THE NODE USER, never root. A root-owned config file freezes the
   gateway.
6. The client-facing product name is Convert and Flow. Never say GoHighLevel and never say GHL
   on any client-visible surface. Internally, the data plane is still the same platform; the
   NAME the client sees is Convert and Flow.
7. CANARY, THEN HOLD. The whole engine is proven on the operator box first. Fleet rollout is
   HELD at repo-only until the operator gives the explicit OK. No client box is touched by the
   build.

## Reuse before rebuild (what this engine binds to, never re-invents)

Reuse fidelity is scored by the build gate. Do not rebuild any of these; bind to them.

| Asset | What it gives this engine | Where it is used |
|---|---|---|
| Skill 57 podcast mode | Script-writer prompt scaffolding, Kie.ai cover prompt, deterministic prover style, golden-fixture pattern, graceful-skip and fail-closed-before-publish postures | Style-engine prompts, Step 10, quality provers, fixtures |
| Skill 35 render plus playbook section 15 | The production Fish render (retry loop plus ffprobe verify), the proven Podbean publish flow via the Convert and Flow content delivery network | Step 11 audio, Step 15 publish |
| Skill 30 Fish Audio reference | Request templates, emotion tag inventory, ffmpeg stitching guidance, the voice standard operating procedure | Steps 6, 11, and the tagging strategy |
| Skill 23 role-library podcast and audio | The professional production doctrine: LUFS targets, four quality gates, guest handling, distribution, key performance indicators, and the personas the engine binds to | Persona binding (Section 11), mastering, quality doctrine |
| Skill 44 caf plus Skill 29 REST | The entire Convert and Flow data plane (Tier 0 caf, Tier 3 REST); Skill 44 workflow discovery and enrollment | Steps 0, 14, 16, 17 |

Boundaries with the sibling skills, so they never diverge: Skill 57 podcast mode remains the
SOCIAL PACKAGING lane; this engine is CANONICAL for full published episodes. Skill 35's
playbook is cross-linked as the productionized Podbean flow. Cross-references are added in both
directions so an edit to one never silently contradicts the other.

## Runtime model routing (never Anthropic at runtime)

This skill is authored offline by the build team. The SHIPPED skill routes ALL content work
through the client's own providers in this fixed cascade and never calls an Anthropic model,
provider, package, key, or host at runtime:

1. Ollama Cloud Kimi 2.6 (thinking high) first.
2. Ollama Cloud GLM 5.2 (thinking high) second.
3. OpenRouter equivalents in the same order.
4. Gemini 3.1 Flash Lite as the final fallback.

The judge tier for semantic quality checks (Gemini 3.1 Flash Lite or GLM 5.2) is DISTINCT from
the writer tier. The writer never grades its own work as the deciding vote. A merge-gate scan
(guard-no-anthropic-runtime) refuses any Anthropic reference in a shipped runtime file and
refuses deny-pattern substitutions at runtime; a prior fleet defect shipped Anthropic to 23 of
32 boxes and this guard exists to make that structurally impossible.

`model_router.py` is the deterministic EXECUTOR of that policy: the single call site every
runtime text turn flows through. It resolves the `content` or `qc_judge` tier from
config/models.json to the client's own priority-ordered provider chain, resolves each lane's
credential by ENV LABEL only (live process env first, reported SET or NOT SET, never a value),
advances the chain on retryable failures (insufficient_credits, auth, rate_limit, timeout,
refusal), meters every call through podcast-cost-ledger.py (a hard cost ceiling blocks the call
before it bills), and on chain exhaustion holds the job durably through credit_queue.py with
exactly ONE deduped founder alert through alert-dedup.py. It refuses at call time any resolved
model, provider, or family that matches the deny_patterns (claude, anthropic, us.anthropic,
opus, sonnet, haiku) or an Anthropic-family shape: a deny match is a HARD ERROR, never a silent
fallback. Every non-primary lane that serves a turn is recorded as a substitution (spooled for
the delivery report) so the model actually used is always named honestly.

    model_router.py validate                  fail-closed check of config/models.json
    model_router.py resolve <content|qc_judge> print a tier chain (SET/NOT SET only)
    model_router.py deny-check <model-id>      exit 2 if the id is denied
    model_router.py route                      JSON {tier,messages,context} on stdin
    model_router.py self-test                  offline routing/deny/exhaustion battery

## Data plane doctrine (Tier 0 caf plus Tier 3 REST only)

Sub-agents get NO Model Context Protocol injection. Therefore the two Model Context Protocol
tiers are structurally UNUSABLE inside this pipeline, because a sub-agent performing a media
upload or a field write-back would silently have no tools, and "silently no tools" is exactly
the class of false-done failure the quality protocol exists to kill. The rule:

- TIER 0, Skill 44 caf command line interface: the PRIMARY data plane for contact reads,
  custom-field writes, and workflow enrollment.
- TIER 3, Skill 29 direct REST: MANDATORY for binary media uploads (there is no other tier
  that performs multipart uploads), and the sub-agent-safe fallback for every Tier 0
  operation.
- The official and community Model Context Protocol tiers are FORBIDDEN in the per-episode
  path. Never escalate to them at runtime.

Escalation is Tier 0 to Tier 3 only, with the same private integration token. A 429 never
escalates anywhere: all tiers share one per-location rate bucket, so tier-hopping on a 429 is
self-harm. On a 429, full stop, read the retry window, schedule exactly one resume, and on a
second consecutive 429 hold-queue the job and alert the founder. Tool-bearing steps execute in
the podcast department agent's OWN turn; sub-agents handle pure content work only.

## Fish Audio facts (pinned; verify the header live at the canary)

- Current model is S2.1 Pro, model id s2.1-pro, selected via HTTP HEADER on POST
  https://api.fish.audio/v1/tts with Bearer auth. The endpoint's enum documentation lags the
  release blog, so the s2.1-pro header value is live-verified during the canary before any
  client content depends on it.
- Voice is the client's OWN private voice model, selected by reference_id (one private voice
  per client). Output is mp3 at 192 kbps. Set condition_on_previous_chunks true for long
  episodes so chunked synthesis stays consistent.
- s2.1-pro-free exists but carries NO service level agreement and may train on inputs. It is
  FORBIDDEN for production client content and the render module structurally refuses it.
- Delivery tags are free-form square brackets for S2.1 Pro (S1 legacy uses parentheses). Tag
  density is roughly one tag every two to five sentences, concentrated at pivots, palette
  governed by the respondent's stated tone.

## State vocabulary (podcast_state.py is the single writer)

Every state change in this engine is written by ONE writer, scripts/podcast_state.py, into
~/.openclaw/podcast-engine/podcast-engine.db (SQLite, WAL) and the intake ledger. No other code
opens the database read-write. The dashboard and the kanban READ this state; they never
recompute it. The status enum below IS the dashboard and kanban vocabulary and this runbook
uses it verbatim.

| status | Client-facing label | Pipeline steps it covers |
|---|---|---|
| `received` | Received | Webhook ingested; Step 0 first-run smoke test and Step 1 ingest |
| `researching` | Researching | Step 3 Research Assistant stage |
| `writing` | Writing | Steps 2, 4, 5, 6, 7, 8 (engines, sizing, blueprint, draft, improvement, read-aloud) |
| `in_qc` | Quality review | Step 9 quality control; increments `attempt_count` per failed attempt |
| `generating_art` | Creating artwork | Step 10 Kie.ai cover plus ffmpeg finalize |
| `producing_audio` | Producing audio | Step 11 Fish Audio synthesis and mastering |
| `publishing` | Publishing | Steps 12 to 16 (documents, book teaser, media upload, Podbean, link-back) |
| `enrolling` | Finalizing | Step 17 enrollment or Personal spreadsheet update |
| `complete` | Live | Step 18 delivered; `completed_at` set; terminal |
| `failed` | Needs attention | Three-strike QC stop or unrecoverable failure after the engine's own retries; founder already alerted; terminal unless re-dispatched through the engine |
| `queued_credit_out` | On hold | A paid service reported insufficient credits mid-run; `queue_state='held'`, `resume_stage` records where to resume; 60-day maximum |

Legal transitions (the writer enforces this matrix; anything else raises):

- Forward path: received to researching to writing to in_qc to generating_art to
  producing_audio to publishing to enrolling to complete.
- QC loop: in_qc to writing (targeted revision) up to three attempts, then in_qc to failed.
- Any non-terminal stage to queued_credit_out; on credit restore, queued_credit_out to
  resume_stage with queue_state='resumed'.
- Required-outputs gate: a forward advance that LEAVES a producing stage is refused (exit 3)
  until that stage's deliverable artifact(s) are recorded, so no job can reach `complete` (or
  slip past publishing) with no stored audio and no Podbean permalink. The requirement set is
  resolved per job from its preset flags, so a document-only preset (Season-Strategy) and a
  non-publishing preset (Episode Asset Pack) are never falsely blocked. `advance --force-waiver
  "<reason>"` overrides the gate and writes an audit event -- including the operator's reason --
  to the job event log; nothing is ever waived silently.
- 60-day cap: queued_credit_out to failed with queue_state='aged_out', payload purged, founder
  notified.
- Any stage to failed on an unrecoverable error after the engine's own retries.

Writer subcommands the pipeline calls (never bypassed):

    podcast_state.py create   --client-id --location-id --contact-id --mode --style \
                              --payload-file <json> [--show-name --host-name]
    podcast_state.py advance  --job-id --to <status> [--note ...] [--cost-delta 0.12] \
                              [--force-waiver "<reason>"]   # override the required-outputs gate;
                                                            # optional operator reason, audited
    podcast_state.py output   --job-id --field <output_column> --value <url|text|number>
    podcast_state.py hold     --job-id --service <kie_ai|ollama_cloud|openrouter|fish_audio>
    podcast_state.py resume   --job-id
    podcast_state.py fail     --job-id --step <name> --error <sanitized text>
    podcast_state.py sweep-aged-out
    podcast_state.py scrub-pii --job-id | --client-id
    podcast_state.py token    mint|revoke|list --client-id ...
    podcast_state.py deactivate-client --client-id --note ...

Idempotency: the inbound handler computes a submission fingerprint and job key before creating
a job; a UNIQUE (client_id, submission_fingerprint) constraint plus the intake ledger's
exclusive-create claim make a redelivered webhook a no-op. A redelivered webhook can never make
a second episode. A one-answer change produces a new job key and therefore a new episode.

## The canonical 18-step pipeline

Step 0 runs once per client before their first episode; Steps 1 to 18 run per episode. Every
step records its transition through podcast_state.py, meters every billable call through
podcast-cost-ledger.py against the ceilings, and routes every failure alert through
alert-dedup.py to the founder only. Nothing is ever silently dropped: a delayed episode is
acceptable, a lost one is not.

STEP 0, FIRST-RUN SMOKE TEST (once per client, not per episode). ghl_credential_gate.py full
mode confirms the custom field map fields exist by exact key (including the double underscore
in podcast_survey__additional_info), the client's own private integration token and Location ID
resolve and pair-prove against the Location, and Podbean, Fish Audio (key plus reference_id),
and Kie.ai credentials are present. Missing custom fields STOP setup and route the client to
support for the snapshot; the engine never creates fields silently.

STEP 1, INGEST. status `received`. Read every survey answer per the custom field map: style,
mode, thesis, tone, the transparency answer, the preferred pronoun (which governs every
reference to the speaker or guest), stories and quotes, additional info, guest first name for
Interview, and release date. Compute the job key, claim the intake ledger, resolve the output
preset. Duplicate deliveries are acknowledged without a second run. Missing required fields are
raised to the OPERATOR, never guessed.

STEP 2, SELECT ENGINES. status `writing`. Load the matching Style Engine (Counter Intuitive,
Vulnerable, Provocative, or Passionate) and Mode rules; confirm arc beats and proportional word
budgets. The engine's arc, persuasion mechanism, and FORMAT are unchanged by this; per the D1
binding ruling (Skill 6 U98) the script's WRITTEN VOICE is GOVERNED by the blend directive —
`scripts/blend_voice_governance.py` resolves it for the selected engine before STEP 6 DRAFT.

STEP 3, RESEARCH ASSISTANT STAGE. status `researching`. Improve and expand every answer without
changing intent, extract three power statements in the respondent's voice, generate the missing
takeaways and findings, and research up to three REAL verified case studies (demographic-matched
where applicable). Use the best available web research tool and name it honestly in the delivery
report; state the limitation plainly if none is wired. Capped at 12 calls. The research package
is FROZEN after this step; every QC retry reuses it. A fabrication failure later unlocks at most
one supplemental research pass of at most four calls.

STEP 4, SIZE. status `writing`. Choose a runtime in the 7 to 15 minute range at 140 words per
minute; 10 minutes (about 1,400 spoken words) is the default sweet spot. Thin material means a
tight short episode, never padding.

STEP 5, BLUEPRINT. status `writing`. Internal only. Title (compelling, edgy, never preceded by
the word Title, immutable after this step), one-sentence thesis, the style signature line
verbatim, every arc beat with content and a word budget summing to the chosen total,
transparency-beat placement, case-study and power-statement placement, opening and final lines
written first.

STEP 6, DRAFT. status `writing`. Full script in Final Draft format: prose only, everything
speakable, numbers and symbols written as spoken, Fish Audio square-bracket tags embedded per
the tagging strategy (roughly one tag every two to five sentences, concentrated at pivots,
palette governed by the respondent's stated tone).

STEP 7, IMPROVEMENT PASS. status `writing`. More compelling, more disruptive, more emotionally
captivating, tone enforced in every paragraph. Forbidden from changing the title or thesis,
removing the transparency beat, adding fabricated material, or inflating length.

STEP 8, READ-ALOUD PASS. status `writing`. Fix anything a mouth would stumble on at speaking
pace.

STEP 9, QUALITY CONTROL (episode gate). status `in_qc`. All 16 Tier 1 hard-fail checks, then
all 10 rubric dimensions at 8 or higher with no averaging, then the honest per-episode
checklist. qc-tier1-mechanical.py runs the deterministic checks at zero model cost; the
semantic checks (fabrication, mode perspective, pronoun correctness) and the rubric run on the
distinct judge tier. qc-attempt-gate.py owns the attempt counter: targeted revisions only (the
frozen research is reused), a hard stop at three failures with a founder notification carrying
the failing checks and the best draft. The QC persona is qc-specialist-podcast and MUST be a
different persona from whichever persona drafted (independence rule).

STEP 10, COVER ART. status `generating_art`. Kie.ai GPT-image-2, 1K square (1024), prompt built
from the respondent's visual description anchored by the episode theme and title; poll with the
bounded backoff schedule; then ffmpeg in-house: confirm square, resize into the 1400 to 3000
range, JPEG, RGB, under 512 kilobytes, spec-valid filename. Never below 1400 square.

STEP 11, AUDIO. status `producing_audio`. Fish Audio s2.1-pro via header with the client's own
reference_id, mp3 at 192; split at natural beat boundaries only if a per-request limit demands
(never mid-sentence, never mid-tag), condition_on_previous_chunks true, ffmpeg-join seamlessly,
master to the Skill 23 loudness doctrine (minus 14 to minus 16 LUFS integrated), verify with
ffprobe. The Skill 35 render script's retry-plus-verify pattern is the base. Filename is the
client name first, then the episode title. The free tier is structurally refused.

STEP 12, DOCUMENTS. status `publishing`. Detect tooling (Google preferred, then Notion, then
plain text last resort). Episode Package rich and fully rendered with no font below 12 point;
Speech Script clean text only. Where Google is the destination, sharing is set to anyone with
the link can edit.

STEP 13, BOOK TEASER (Interview mode ONLY; Personal mode skips entirely). status `publishing`.
First-chapter book intro, at most three pages, in the person's own voice, ending on a
cliffhanger, built only from what they shared plus verified research, written on Kimi 2.6 or
GLM 5.2, rendered as a book-typeset PDF with no font below 14 point. The book teaser is the
coup de grace of the SHUA experience.

STEP 14, STORE MEDIA. status `publishing`. Tier 3 REST upload of the MP3, cover, and teaser PDF
into the client's Convert and Flow media library folders (podcast, podcast images, podcast
episodes; create-once, reuse-forever, case-insensitive matching); HEAD-verify every returned
public URL. Runtime never depends on folder creation succeeding mid-episode; it only looks up
folders that setup ensured.

STEP 15, PUBLISH TO PODBEAN. status `publishing`. Publishing uses BlackCEO's SINGLE Podbean
OAuth app (client_id and client_secret). The operator HOSTS every client's show under his ONE
Podbean account, so those app credentials are NEVER the client's, are NEVER asked from the
client, and NEVER need to sit on the client box: at runtime they are injected by the operator's
n8n Podbean credential broker (config/n8n/podbean-broker.workflow.json), which mints a
short-lived access token SCOPED to the client's channel (Podbean multiplePodcastsToken). The ONE
Podbean value the client supplies is their Podbean Channel ID (podcast_id) - it selects which
show under the host account is theirs and is not a secret. Flow: obtain a channel-scoped token
from the broker (falling back to a local client_credentials mint only on the operator's own box);
episode number is count plus one; the title convention appends "Inspired by" plus the speaker's
name; uploadAuthorize then PUT for audio and image; create the episode (status publish, or draft
or scheduled when the release date is future); capture the permalink. Idempotent: if the ledger
already holds a permalink, skip.

STEP 16, LINK BACK. status `publishing`. Write the title, description, Episode Package link, and
Speech Script link (and the book_teaser link when that field exists) in ONE batch, then write
the episode URL field ALONE and LAST because it is a live customer-facing trigger for the
downstream workflow. Read back every field byte-for-byte; a mismatch retries once, then enters
failure handling.

STEP 17, TRIGGER AND ENROLL (mode-dependent). status `enrolling`. Interview: verify whether the
URL write already field-triggered the "podcast is completed" workflow, enroll explicitly only
if not, enroll the "podcast episode is ready" workflow per the discovered trigger mechanism, and
verify both via caf reads. Personal: append the episode row to the running spreadsheet, no
workflows, no messages. A hard mode guard in code refuses workflow enrollment in Personal mode.

STEP 18, DELIVER. status `complete`. The deliverable is the pure script plus links. The delivery
report (title, honest word count, runtime, style, mode, writing model including any
substitution, research tool, document destination and links, media locations, Podbean link,
Convert and Flow save confirmations, enrollment confirmation, image prompt, completed
checklist, rubric scores) goes to the OPERATOR channel only, never inside the script, never to
the customer. The engine STOPS here. Convert and Flow owns all messaging.

## The four output-type presets

A preset is a named bundle of mode, pipeline scope, and deliverable set, selected at intake and
carried in the canonical payload and the ledger (default derivable from mode when absent).
Presets 3 and 4 are thin variations over the SAME pipeline and state machine, not separate
systems.

1. INTERVIEW (mode: interview_style_podcast). Full 18-step run. Deliverables: published
   episode, cover, Episode Package, Speech Script, book teaser PDF, workflow enrollment. This
   is the SHUA lead generation lane.
2. SOLO (mode: personal_podcast_style). Full run minus the teaser and the workflows; the
   running spreadsheet is updated instead. The client's own weekly episode in the cloned voice.
3. SEASON-STRATEGY. A planning deliverable, not an episode: season arc, episode slate, style
   and mode per slot, drawing on the Skill 23 director-of-podcast doctrine. Runs the research
   stage and the build gate's document quality checks; skips Steps 6 to 17; produces an Episode
   Package-style strategy document only. No render, no publish.
4. EPISODE ASSET PACK. Regenerates or completes the asset set (cover, documents, teaser) for an
   EXISTING episode without re-writing or re-publishing audio; idempotent against the ledger.
   Useful for repairs and for the sanctioned Skill 57 social-packaging handoff.

## The two quality gates (never conflated, never averaged)

There are TWO gates and they are never substituted for each other. One decides whether BUILD
WORK merges; the other decides whether an EPISODE ships. A build unit scoring 9.0 says nothing
about an episode, and a perfect episode says nothing about merge readiness.

GATE A, BUILD/MERGE. The fleet 10-category rubric at threshold 8.5. Below 8.5 the executing
agent fixes the work and re-runs; at or above 8.5 the work pushes and merges. The rubric decides
quality; nobody asks the founder for a green light the rubric already grants. Riding with Gate
A: guard-no-anthropic-runtime, guard-cron-inventory, the content-hash restamp gate, the
annotated-tag gate, the fleet-wide client-name grep, and the update.sh skill-count check.

GATE B, EPISODE. Three instruments in order: the 16 Tier 1 hard-fail binary checks (any single
failure means NOT deliverable), then the 10-dimension quality rubric at 8 or higher on EVERY
dimension with no averaging, then the honest per-episode checklist reproduced in the delivery
report. Independence: the judge tier is distinct from the writer tier and qc-specialist-podcast
is a different persona from the drafter. Read protocol: three passes with different jobs
(mechanics and forbidden content; structure and fidelity; full read-aloud at speaking pace),
none skipped because the episode feels done. Failure loop: targeted revision only, hard stop at
three attempts, founder notified through alert-dedup with the failing checks and the best draft.
Standards are never relaxed to resolve a three-strike failure.

The 16 Tier 1 checks, in one line each: 1 zero em dash characters; 2 no triple backticks or
code-fence markers; 3 no markdown in the script; 4 no labels or speaker prefixes or stage
directions; 5 the word Title never precedes the title; 6 speakable characters only; 7 tag
syntax integrity for the target model; 8 word and character counts recomputed with tags
stripped; 9 word-count honesty; 10 no forbidden reference-speaker names, books, or talks; 11 the
style-forbidden word never appears; 12 no fabrication anywhere; 13 mode perspective correct
(Personal first person throughout, Interview host first person and guest third person by name);
14 pronoun correctness against the stated preferred pronoun; 15 pure deliverable, the episode and
nothing else; 16 no intake contamination.

## Role bindings (Skill 23 personas; do not invent parallels)

Access follows the chain of custody. The podcast department (id `podcast`, universal_primary
true, on the universal floor) is the OWNER; the intake session binds to its agent.

- director-of-podcast owns the run end to end, the kanban card, preset selection, and the
  3-strike escalation to the founder.
- podcast-host is the voice-and-framing persona consulted for Personal mode tone fidelity and
  Interview mode show framing (Steps 5 to 8).
- audio-post-producer owns Steps 10 and 11 (art finalization, render, stitch, LUFS mastering)
  plus media quality control; podcast-editor and mastering support repair passes.
- qc-specialist-podcast owns Step 9 and MUST be a different persona from the drafter.
- podcast-producer supports director-of-podcast for Season-Strategy presets.

Read-only downstream consumers: the social and marketing departments may read completed episode
records and published links (the Episode Asset Pack preset is the sanctioned handoff) with ZERO
write access to the pipeline or its state. The master agent ROUTES inbound podcast jobs to the
podcast department and never executes a pipeline step. Sales, finance, legal, and
personal-assistant departments get NO access; customer messaging belongs to Convert and Flow.

## Cost and furnace guardrails (bounded by design)

- Ceilings: soft 2.50 and hard 5.00 dollars per episode, 15.00 per client per day, at most 3
  episodes per client per day, 400,000 content tokens per episode, 8,000 output tokens per call.
- Exactly ONE recurring cron per client: a daily smoke test (client morning, jittered, at most
  1 cent per run, balance endpoints only, never model turns) that also ages and drains the
  credit-out queue. No heartbeat entry ever, no queue poller, no per-job watchers; the dashboard
  triggers nothing. guard-cron-inventory.py enforces this and a departed client leaves zero
  recurring jobs.
- Research runs ONCE and is frozen; QC retries are targeted, not full rewrites (worst case about
  1.6x a single write). Tier 1 QC is deterministic string work at zero dollars. Web research is
  capped at 12 calls per episode.
- Alert dedup: one alert per client-service-failure class per 6-hour window, at most 4 founder
  alerts per client per day, then a digest. All Telegram goes through the gateway only.

## Loop engineering (continuous and self-correcting)

Every episode is a durable state machine (TaskFlow plus intake ledger plus SQLite). Every
failure has a typed handler: a QC failure loops through targeted revision to the 3-strike cap; a
credit-out holds the job with full payload and partial state and resumes from resume_stage on
credit restore (60-day maximum, daily age-check); a rate limit full-stops and reschedules; a
crash resumes idempotently from the last recorded state. The daily smoke test is the loop's
heartbeat substitute: one bounded probe that also drains the queue. Nothing is ever silently
dropped.

## Writing rules (verbatim, enforced by qc-tier1-mechanical.py)

Binding on this document and on everything the skill ever produces:

- ZERO em dash characters anywhere.
- NO triple backtick fences and no code-fence markers of any kind inside any produced JSON,
  HTML, or script output.
- NO markdown inside a produced script: no asterisks, headers, bullets, numbered lists, or bold
  or italic markers.
- Final Draft format for every script: prose only, everything speakable, numbers and symbols
  written as spoken, no labels, no speaker prefixes, no stage directions, the title woven into
  natural speech and never preceded by the word Title.
- Word-count honesty is absolute: the true spoken count is reported with tags stripped;
  misreporting any check is an absolute failure. Genuine input limitations are noted plainly,
  never faked into a pass.

## Per-client credentials (labels and locations only, never values)

These are the NAMED CLIENT's OWN accounts (the ONE exception is the Podbean OAuth app, which is
BlackCEO's single shared app brokered via n8n - see the Podbean row); no operator, shared,
agency, or other-client credential ever substitutes for the per-client ones. Verification is
always SET or NOT SET plus a behavior probe; a value is never printed, echoed, grepped, or pasted.

- Fish Audio API key and voice reference_id: client env stores (live process env first) and the
  Fish Audio skill config.
- Kie.ai API key: client env stores and the kie.ai skill config.
- Convert and Flow private integration token (prefix pit-) and Location ID: client env stores
  via the shared alias resolver; the Location ID must equal the webhook payload's location_id.
- Podbean: the ONLY per-client Podbean value is the Podbean Channel ID (podcast_id) - the
  client's show under BlackCEO's host account, captured at onboarding, never a secret, never
  guessed by the mapper. The Podbean OAuth app client_id and client_secret are BlackCEO's SINGLE
  shared app, NOT the client's: they live only inside the operator's n8n Podbean broker
  (config/n8n/podbean-broker.workflow.json), are injected at runtime, and are NEVER asked from
  the client. Broker mode (fleet default): the client box holds only PODBEAN_BROKER_WEBHOOK_URL +
  PODBEAN_BROKER_TOKEN + the Channel ID - no Podbean secret ever lands on it. Local fallback
  (operator's OWN box only): PODBEAN_CLIENT_ID + PODBEAN_CLIENT_SECRET resolve from the operator
  env. Selection is per box: broker if the webhook URL and broker token both resolve, else local.
- Ollama Cloud API key or OpenRouter API key: client env (the ollama-cloud provider needs a
  baseUrl, not an apiKey slotting).
- PODCAST_INTAKE_HOOK_SECRET and PODCAST_DASHBOARD_TOKEN: generated at provisioning, stored in
  the client env or a 0600 secrets file.
- CLOUDFLARE_API_TOKEN is BlackCEO's OWN, operator side only, never on a client box; never trust
  CLOUDFLARE_ZONE_ID.

## Enforcement pointers (a rule without a gate is a suggestion)

| Rule | Enforced by |
|---|---|
| State transitions, one writer, redaction | scripts/podcast_state.py |
| Cost ceilings and token budgets | scripts/podcast-cost-ledger.py |
| 16 Tier 1 deterministic checks | scripts/qc-tier1-mechanical.py |
| Attempt counter, frozen research, 3-strike | scripts/qc-attempt-gate.py |
| Credential resolution, pairing, fingerprint | scripts/ghl_credential_gate.py |
| No Anthropic in shipped runtime | scripts/guard-no-anthropic-runtime.py |
| Exactly one cron, no heartbeat, churn sweep | scripts/guard-cron-inventory.py |
| Alert dedup and storm cap, gateway-only | scripts/alert-dedup.py |
| Daily funded-reachability smoke test | scripts/podcast-smoke-test.py |
| Facebook-ads activation checklist item never drifts out of the client-onboarding runbook (SOP-PODCAST-02 Section 2.9) | scripts/guard-runbook-fb-activation-checklist.py |

If the repo is not updated, it is not done. A sub-agent's claim of done is a hypothesis until
independently verified.
