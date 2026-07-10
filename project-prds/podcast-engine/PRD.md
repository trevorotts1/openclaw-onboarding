# PODCAST PRODUCTION ENGINE, PRODUCT REQUIREMENTS DOCUMENT
## The True, Hyper-Extensive PRD for the Podcast Production Engine OpenClaw Skill
### Version 1.0, authored by Fable, 2026-07-06. Status: READY FOR /goal EXECUTION.

Document control: this is the TRUE PRD. During the build, the execution agents copy this PRD set (PRD, CHECKLIST, TODO, WAVE-PLAN, SESSION-LOG, CHANGE-LOG, QC-PROTOCOL-AND-MATRIX) into the onboarding repo master files at project-prds/podcast-engine/ and keep both copies in sync. This folder at <OPERATOR_HOME>/clawd/projects/Podcast-Production-Engine/ remains the operator-side working copy. The design/ subfolder in this project holds the five completed design specs and is referenced, never modified, by this plan.

Writing rules binding on this document and on everything the skill ever produces: zero em dash characters, no triple backtick code fences inside produced JSON, HTML, or script outputs, and loop-engineering framing throughout.

---

## 1. WHAT THE COMPANION DOCUMENT IS, WHY IT EXISTS, AND ITS PURPOSE

The companion document is PODCAST_EPISODE_GENERATION_SYSTEM.md (Master AI Instructions v3.1, 1157 lines, at <OPERATOR_HOME>/Downloads/PODCAST_EPISODE_GENERATION_SYSTEM.md). It is the complete operating manual for an AI system that takes a completed podcast intake survey and produces a fully written, produced, and published podcast episode with zero human editing between the AI and the listener. It was created iteratively with the founder (Trevor Otts, BlackCEO) to capture every rule of the process: intake and the OpenClaw inbound webhook, four writing Style Engines (Counter Intuitive, Vulnerable, Provocative, Passionate), two Production Modes (Personal Podcast and Interview Style), the mandatory Research Assistant stage, length and pacing, Fish Audio delivery tags, the Final Draft format, image generation via Kie.ai GPT-image-2, audio via Fish Audio, document creation, the Convert and Flow custom field map, the Podbean publishing pipeline, mode-dependent workflow enrollment via Skill 44, mandatory credentials, health and credit resilience, and a client dashboard.

Why it exists: the interview-style path is, for the business, primarily a lead generation engine built on the founder's SHUA principle (Seen, Heard, Understood, Acknowledged). The finished episode is a gift engineered to make the guest feel all four, and the book teaser bonus is the coup de grace of that experience. Quality is therefore not negotiable: the output goes directly from text-to-speech to a listening audience, so precision failures are business failures. The Personal Podcast path serves clients producing their own weekly episodes in their own cloned voice.

Its purpose in this build: it is the authoritative brain of the new skill. The companion document says WHAT the skill does. CLAUDE_CODE_BUILD_BRIEF.md (at <OPERATOR_HOME>/Downloads/CLAUDE_CODE_BUILD_BRIEF.md) says HOW to build it. This PRD synthesizes both, plus the five completed design specs, plus verified research and fleet doctrine, into the single execution-ready plan. Where the companion document leaves a gap, this PRD names the gap and the design that closes it (Section 10). Every hard rule in the companion document is preserved verbatim in behavior: the em dash ban, the no-triple-backticks rule, the Final Draft format, the episode QC protocol with its three-strike cap, the credit-out queue with the 60-day maximum, the responsibility boundary (the agent enrolls and stops, Convert and Flow runs all customer messaging), and the standardized custom field map exactly as written.

---

## 2. PRODUCT DEFINITION AND DESIGN INTENT

The Podcast Production Engine is a per-client OpenClaw skill that turns one intake survey submission into one published podcast episode, end to end, autonomously, on the client's own box, with the client's own credentials, at a bounded cost, with independent quality control, full durability, and a client-facing dashboard.

DESIGN INTENT (the fusion): the fleet already owns two mature podcast lanes and this engine FUSES them rather than inventing a third:

1. The Fish-render solo/AI-voice lane: Skill 35's production Fish Audio render script, Skill 30's Fish Audio API reference and voice standard operating procedure, Skill 57's podcast mode (script writer prompt, Kie.ai cover prompt, deterministic QC provers, golden fixture). This lane knows how to WRITE and RENDER.
2. The Skill 23 interview/produced doctrine: role-library/podcast/ (director-of-podcast, podcast-host, audio-post-producer, qc-specialist-podcast, the department how-to guide and suggested roles) plus role-library/audio/ (podcast-editor, podcast-producer, mastering). This lane knows how to RUN A PROFESSIONAL PODCAST OPERATION: loudness mastering at minus 14 to minus 16 LUFS, four quality gates, guest handling, distribution and RSS, key performance indicators.

The engine binds the render lane to the doctrine lane through output-type presets (Section 8) so one skill serves both a solo founder recording a weekly personal episode and an interview-style lead generation machine. The engine is INTEGRATION plus HARDENING of assets we already own, not a from-scratch build. Reuse before rebuild is a scored requirement of the build QC gate.

---

## 3. NON-NEGOTIABLE GROUNDING DECISIONS

These are settled. Execution agents do not relitigate them.

1. VERSION: the live onboarding repo (trevorotts1/openclaw-onboarding) content version is currently v17.0.45. The build brief's "bump to version 18 (major)" therefore resolves to v18.0.0 as the capstone major bump. The v10.x figure in the stale master-files snapshot is NOT the live baseline; ignore it. Release tags MUST be annotated (git tag -a) and the tag MUST be created BEFORE the merge or the G1 gate rejects it. update.sh's skill count must be corrected for the new skill. _index.json content_sha must be re-stamped (hash-content-manifest.py) after ANY role or skill edit or the CONTENT-HASH gate fails.
2. TWO SEPARATE QC GATES, never conflated (full detail in QC-PROTOCOL-AND-MATRIX.md): the BUILD/MERGE gate is the fleet 10-category rubric at the 8.5 threshold and decides whether work merges; the EPISODE gate is the companion document's 16 Tier 1 hard-fail checks plus the 10-dimension rubric at 8 or higher per dimension plus the 3-strike cap, and decides whether an episode is deliverable.
3. BUILD-TIME versus RUNTIME model boundary: Opus 4.8 and Fable build the skill. The SHIPPED skill routes all content work to Ollama Cloud (Kimi 2.6 first, then GLM 5.2, thinking high), then OpenRouter equivalents in the same order, then Gemini 3.1 Flash Lite as final fallback. NOTHING Anthropic ships in any runtime file. A prior build defect shipped Anthropic to 23 of 32 boxes; guard-no-anthropic-runtime.py (furnace design, Guardrail 5) enforces this at the merge gate and refuses deny-pattern substitutions at runtime.
4. SUB-AGENTS GET NO MCP INJECTION. Therefore the entire Convert and Flow data plane is Skill 44 caf command line interface (Tier 0) first and Skill 29 direct REST (Tier 3) second, with Tier 3 mandatory for binary media uploads. The two MCP tiers are structurally forbidden inside the pipeline (ghl-design.md Section 1). Tool-bearing steps execute in the podcast agent's own turn; sub-agents handle pure content work only.
5. THE PODCAST DEPARTMENT ALREADY EXISTS: content-creator pack, universal_primary true, id "podcast", on the 28-department universal floor enforced by department-floor.py. The build WIRES the skill and roles into it. Creating a duplicate department is a build failure.
6. PODCAST PERSONAS ALREADY EXIST (Skill 23 role-library/podcast/ and role-library/audio/). Persona matching binds to them. Inventing parallel personas is a build failure.
7. FISH AUDIO CURRENT FACTS (verified research, bake in, do not re-research; verify the model header live at build time): current model is S2.1 Pro, model id s2.1-pro, NOT plain S2. Endpoint POST https://api.fish.audio/v1/tts, Bearer auth, model selected via HTTP HEADER (the endpoint's enum documentation lags the release blog, so verify the s2.1-pro header value with a live call during the canary). Voice selection is via reference_id: one private voice model per client, managed through the voices and instant-voice-clone APIs. Pricing 15 dollars per 1 million UTF-8 bytes, roughly 60 cents per 30-minute episode. Concurrency is gated by cumulative prepaid spend: under 100 dollars gives 5 concurrent, 100 dollars and up gives 15, 1000 dollars and up gives 50. Delivery tags are free-form square brackets (24 basic plus 25 advanced emotions plus tone, effect, and pause tags); S1 legacy uses parentheses. Output mp3 at 192 kbps; set condition_on_previous_chunks true for long episodes so chunked synthesis stays consistent. s2.1-pro-free exists but has NO service level agreement and may train on inputs: FORBIDDEN for production client content, enforced in the render module.
8. FLEET DOCTRINE BINDING ON THE BUILD: onboarding repo is a single merge-writer (build in parallel on branches and pull requests only, MERGE SERIAL; never stack big fan-outs, roughly 40 or more concurrent sub-agents trips a server rate limit, so stagger and use resumeFromRunId); the operator box is the CANARY and the whole build is proven there first; fleet rollout is HELD at repo-only per the current campaign posture until the operator gives the OK; MOVE IN SILENCE (zero client-facing messages, operator-verbose only, suppress owner alerts during maintenance, never run qc-completeness.sh standalone because it leaks a client Telegram alert); never print secret values (credentials are documented by label and location, never value); never commingle clients (the named client's own keys only); config writes run as the node user, never root (root-owned config freezes the gateway); the client-facing name is Convert and Flow, never GoHighLevel and never GHL in any client-visible surface.

---

## 4. FULL ARCHITECTURE

Per-client topology (every client runs their own OpenClaw on their own box, Mac mini or Virtual Private Server):

    Upstream intake (Convert and Flow workflow webhook action, Make.com, or n8n)
      POST https://<slug>-hooks.zerohumanworkforce.com/... (BlackCEO Cloudflare zone)
        -> Cloudflare Tunnel (the client's ONE existing named tunnel, new ingress rules only)
          -> loopback 127.0.0.1:18789 OpenClaw gateway
            -> Webhooks plugin route podcast-intake-<slug> (per-client SecretRef, env PODCAST_INTAKE_HOOK_SECRET)
              -> deterministic intake handler (no language model, no MCP): parse, map by meaning,
                 tenant check, dedup claim, persist, fast acknowledge
                -> durable TaskFlow, flow id = job_key, on sessionKey podcast:intake:<slug>
                  -> the client's podcast department agent executes Steps 1 to 18
                    -> writes every state change through ONE writer (podcast_state.py) into
                       ~/.openclaw/podcast-engine/podcast-engine.db (SQLite, WAL) and the intake ledger
                      -> dashboard service 127.0.0.1:4010 (read-only) behind
                         <slug>-podcast.zerohumanworkforce.com + Cloudflare Access
                      -> kanban and client dashboard both read the same state, never recompute

    Egress per episode: Kie.ai (cover art) -> ffmpeg (square, compress) -> Fish Audio s2.1-pro
    (audio, reference_id voice) -> ffmpeg (stitch, master) -> documents (Google preferred, Notion,
    plain text last resort) -> Convert and Flow media library (Tier 3 REST upload) -> Podbean
    (OAuth client_credentials, uploadAuthorize, episode create, permalink) -> Convert and Flow
    custom field writes (caf, URL field LAST and ALONE) -> Skill 44 enrollment (Interview mode)
    or running spreadsheet update (Personal mode) -> STOP. Convert and Flow owns all messaging.

Component inventory (each maps to a design spec section and a build wave):

- Inbound webhook layer: design/webhook-design.md. Webhooks plugin route, per-client secret, job key (pd- prefix, contact_id plus first 16 hex of the sha256 of the canonical submission), intake ledger with exclusive-create claim, meaning-based deterministic mapper with alias tables and value-shape validation, hard tenant check on location_id, fast-acknowledge contract, 409 read-check-reapply helper, T1 to T9 onboarding verification suite.
- Convert and Flow data plane: design/ghl-design.md. Tier 0 caf plus Tier 3 REST only; 11-alias (expanding to 15 plus with the CONVERTFLOW additions in the SHARED resolver) credential resolution with the ENV-CHECK-BEFORE-FAIL sequence; field-key to field-id map cached in per-client state; write ordering with podcast_survey_episode_url written last and alone because workflow 04 is field-change triggered; media uploads via POST /medias/upload-file with public-reachability HEAD verification; Skill 44 enrollment with discovery-then-verify-then-enroll and a hard mode guard refusing Personal mode; per-location rate budget (100 per 10 seconds burst, 200,000 per day) with probe-before-bulk and full-stop on 429; ghl_credential_gate.py guardrail with exit codes for missing, isolation violation, missing fields, and rate floor.
- Cloudflare layer: design/cloudflare-design.md. DECISION: BlackCEO-hosted, firm. Account <CF_ACCOUNT_ID>, zone zerohumanworkforce.com <CF_ZONE_ID> (hardcode or resolve by name; the CLOUDFLARE_ZONE_ID environment variable on the operator box points at the WRONG zone and must never be trusted). One tunnel per client, new hostnames <slug>-podcast (dashboard, Access allow-by-email) and <slug>-hooks (webhooks, no Access, WAF POST-only rule, reuse an existing hooks hostname when one exists). Full 9-step revocation runbook including edge-only emergency mode, plus the mirror provisioning script. Every endpoint shape is LIVE-VERIFY at build time.
- Furnace and cost guardrails: design/furnace-design.md. One daily smoke-test cron per client (6:00 AM client time, jittered, at most 1 cent per run, balance endpoints never model turns); cost ceilings (soft 2.50, hard 5.00 per episode, 15.00 per client per day, 3 episodes per client per day, 400,000 content tokens per episode, 8,000 output tokens per call); research runs ONCE and is frozen (QC retries reuse it; one supplemental pass of at most 4 calls only on a fabrication failure); targeted retries not full rewrites (worst case roughly 1.6x single-write cost); Tier 1 QC is deterministic string work at zero dollars; web research capped at 12 calls per episode; runtime model tiering with deny patterns; alert dedup (one alert per client-service-failure class per 6-hour window, 4 founder alerts per client per day then digest); cron inventory audit (exactly one recurring job per client, no heartbeat entry ever); churn cleanup leaving zero recurring jobs behind. Worst-case daily spend per client with all guardrails: 15.01 dollars; idle client: 1 cent.
- Client dashboard: design/dashboard-design.md. A /podcast route group INSIDE the existing Command Center app (Next.js 14.2 App Router, better-sqlite3 read-only), pixel-identical to the Command Center design system, brand variables flowing through BrandTheme. SQLite schema podcast-engine.db (podcast_jobs, podcast_job_events, podcast_job_payloads, podcast_dashboard_tokens, podcast_client_state) written ONLY by podcast_state.py with a legal-transition matrix. Client-clean versus operator-verbose views enforced at the API serializer boundary. Revocable dashboard tokens (hash-only storage), three-blade kill switch (application, edge, engine), PII isolation with payload purge and 90-day tombstone scrub. Fourteen independently verifiable acceptance criteria. Built by a dedicated Fable sub-agent.
- Guardrail script suite (the enforcement layer the build brief mandates): podcast_state.py (sole writer), podcast-cost-ledger.py (metering choke point), podcast-smoke-test.py, qc-tier1-mechanical.py, qc-attempt-gate.py, alert-dedup.py, ghl_credential_gate.py, guard-no-anthropic-runtime.py, guard-cron-inventory.py, provision-podcast-client.sh, revoke-podcast-client.sh, and the T1 to T9 webhook verification script. Enforcement, not description: every rule names a script, a threshold, and an enforcement point.

---

## 5. THE CANONICAL 18-STEP PIPELINE

Step 0 (once per client, before their first episode, not per episode): first-run smoke test. ghl_credential_gate.py full mode: custom_field_map fields exist (exact keys, including the double underscore in podcast_survey__additional_info), client's own private integration token and Location ID resolve and pair-prove against the Location, the Podbean broker reachable (broker mode) or the shared Podbean app present (operator box only) plus the client's Podbean Channel ID (podcast_id) captured, Fish Audio key and reference_id present, Kie.ai key present. Missing custom fields: STOP, tell the client to contact support for the snapshot; never create fields silently.

1. INGEST. Read every survey answer per the custom field map: style, mode, thesis (Q1, plus Q2 for Provocative), tone, transparency answer (contact.podcast_interview_smiq), preferred pronoun (contact.my_preferred_pronoun, governs every reference), stories and quotes, additional info, guest first name (Interview), release date. State: received.
2. SELECT ENGINES. Load the matching Style Engine and Mode rules, confirm arc beats and proportional word budgets.
3. RESEARCH ASSISTANT STAGE. Improve and expand every answer without changing intent, extract three power statements, generate missing takeaways and findings, research up to three REAL verified case studies (demographic-matched where applicable), assemble the research package. Perplexity if wired, else the best available web research tool, else state the limitation honestly. Capped at 12 calls (furnace Guardrail 4). The package is FROZEN after this step; QC retries reuse it. State: researching.
4. SIZE. Choose runtime in the 7 to 15 minute range at 140 words per minute; 10 minutes (about 1,400 spoken words) is the sweet spot and the default. Thin material means a tight short episode, never padding.
5. BLUEPRINT. Title (compelling, edgy, never preceded by the word Title, immutable after this step), one-sentence thesis, the style signature line verbatim, every arc beat with content and word budget, transparency beat placement, case study and power statement placement, opening and final lines written first. Internal only.
6. DRAFT. Full script in Final Draft format: prose only, everything speakable, numbers and symbols written as spoken, Fish Audio square-bracket tags embedded per the tagging strategy (one tag roughly every two to five sentences, concentrated at pivots, palette governed by the respondent's stated tone). State: writing.
7. IMPROVEMENT PASS. More compelling, more disruptive, more emotionally captivating, tone enforced in every paragraph. Forbidden from changing the title or thesis, removing the transparency beat, adding fabricated material, or inflating length.
8. READ-ALOUD PASS. Fix anything a mouth would stumble on at speaking pace.
9. QUALITY CONTROL (episode gate). All 16 Tier 1 hard-fail checks, then all 10 rubric dimensions at 8 or higher, then the per-episode checklist honestly completed. qc-tier1-mechanical.py runs the deterministic checks at zero cost; the semantic checks (fabrication, mode perspective, pronoun correctness) and rubric scoring run on the cheap judge tier. qc-attempt-gate.py owns the attempt counter: targeted revisions, hard stop at three failures with a founder notification carrying the failing checks and the best draft. State: qc.
10. COVER ART. Kie.ai GPT-image-2, 1K square (1024), prompt built from the respondent's visual description anchored by the episode theme and title; poll with the bounded backoff schedule; then ffmpeg in-house: confirm square, resize into the 1400 to 3000 range, JPEG, RGB, under 512 kilobytes, spec-valid filename. Never below 1400 square. State: art.
11. AUDIO. Fish Audio s2.1-pro with the client's own reference_id, mp3 at 192; split at natural beat boundaries if a per-request limit demands (never mid-sentence, never mid-tag), condition_on_previous_chunks true, ffmpeg-join seamlessly, master to the Skill 23 loudness doctrine (minus 14 to minus 16 LUFS integrated), verify with ffprobe (the Skill 35 render script's retry-plus-verify pattern is the base). Filename: client name first, then episode title. State: audio.
12. DOCUMENTS. Detect tooling (Google preferred, then Notion, then plain text). Episode Package rich and fully rendered (no font below 12 point); Speech Script clean text only. Google sharing: anyone with the link can edit.
13. BOOK TEASER (Interview mode ONLY). First-chapter book intro, at most three pages, the person's own voice, cliffhanger ending, built only from what they shared plus verified research, written on Kimi 2.6 or GLM 5.2, rendered as a book-typeset PDF with no font below 14 point. Personal mode skips entirely.
14. STORE MEDIA. Tier 3 REST upload of MP3, cover, and teaser PDF into the client's Convert and Flow media library folders (podcast, podcast images, podcast episodes; create-once reuse-forever with case-insensitive matching); HEAD-verify every returned public URL. State: publishing.
15. PUBLISH TO PODBEAN. OAuth client_credentials using BlackCEO's SINGLE Podbean app, injected at runtime by the n8n Podbean broker (never the client's, never asked, never required on the client box; local client_credentials mint is a fallback only on the operator's own box), minting a token scoped to the client's Podbean Channel ID (podcast_id, the only Podbean value the client supplies); episode number = count plus one; title convention appends "Inspired by" plus the speaker's name; uploadAuthorize then PUT for audio and image; create the episode (status publish, or draft/scheduled when contact.date_for_release is future); capture the permalink. Idempotent: if the ledger already holds a permalink, skip.
16. LINK BACK. Write title, description, Episode Package link, Speech Script link (and book_teaser when the field exists) in one batch, then write contact.podcast_survey_episode_url ALONE and LAST (it is a live customer-facing trigger for workflow 04). Read back every field byte-for-byte; a mismatch retries once then enters failure handling.
17. TRIGGER AND ENROLL (mode-dependent). Interview: verify whether the URL write already field-triggered 04-Podcast is Completed, enroll explicitly only if not, enroll 06-Podcast_Episode_Is_Ready per the discovered trigger mechanism, verify both via caf reads. Personal: append the episode row to the running spreadsheet, no workflows, no messages. Hard mode guard in code. State: enrolling.
18. DELIVER. Pure script plus links as the deliverable; the delivery report (title, honest word count, runtime, style, mode, writing model including any substitution, research tool, document destination and links, media locations, Podbean link, Convert and Flow save confirmations, enrollment confirmation, image prompt, completed checklist, rubric scores) goes to the operator channel, never inside the script, never to the customer. State: complete.

Cross-cutting at every step: podcast_state.py records the transition (dashboard and kanban read it); podcast-cost-ledger.py meters every billable call against the ceilings; any insufficient-credits error moves the job to the credit-out queue with full payload and partial state (60-day maximum, daily age-check, resume from resume_stage); every failure alert routes through alert-dedup.py to the founder only.

---

## 6. THE FIVE DESIGN SPECS, WOVEN IN

Each design is complete and approved for build; this section states what each one contributes and the binding interfaces between them. Execution agents read the full specs in design/.

6.1 WEBHOOK (design/webhook-design.md). Decision: OpenClaw Webhooks plugin routes, not shared gateway-native hooks (per-client SecretRef, durable TaskFlows, deterministic session routing; the mapped-hook fallback is a documented degraded mode with five simultaneous preconditions). Contributes: the job key and canonical-hash dedup ("a redelivered webhook can never make a second episode"), the intake ledger at ~/.openclaw/state/podcast-engine/intake-ledger/ with exclusive-create claim, the meaning-based mapper (deterministic Python, unit-tested over fixture payloads from each upstream family, never a model call), the hard tenant check making cross-client contamination structurally impossible, the fast-acknowledge rule, the 409 read-check-reapply contract, the _test flag short-circuit, and the T1 to T9 verification table that gates every client go-live. Interfaces: flow id equals job_key; sessionKey podcast:intake:<slug> is owned by the podcast department agent; the ledger state enum IS the dashboard and kanban vocabulary; the double-publish guard (permalink check before publish, field-equality check before write, enrolling-before-complete states) is implemented by the pipeline.

6.2 CONVERT AND FLOW (design/ghl-design.md). Decision: Tier 0 caf plus Tier 3 REST only; MCP tiers forbidden in the pipeline because sub-agents get no MCP injection. Contributes: the credential resolver (with the recommended CONVERTFLOW aliases landing in the SHARED resolver used by Skills 29, 36, and 44, followed by a content_sha restamp), the ENV-CHECK-BEFORE-FAIL sequence, the pairing proof and anti-commingling fingerprint, the field-key to field-id cached map, the write ordering with the URL last, read-back verification, media folder create-once logic with the folder-create endpoint verified against the Skill 29 catalog at build time (Tier 4 one-time onboarding fallback only if REST truly lacks it), Skill 44 workflow discovery at setup (never guessed) and verify-then-enroll at runtime with the double-enrollment guard, rate budgeting with probe-before-bulk and full-stop-on-429, and ghl_credential_gate.py.

6.3 CLOUDFLARE (design/cloudflare-design.md). Decision: BlackCEO-hosted, firm, with the tradeoff table recorded. Contributes: the tunnel topology (one existing tunnel per client, add ingress; dashboard on loopback 4010; hooks hostname reused when present), the zone-id trap warning, the layered webhook auth (route secret primary, WAF POST-only rule, optional Access service token documented as a hardening option only), the dashboard access path (Access allow-by-email: the client's emails plus <operator-email-alt> plus <operator-email>, one-time PIN or Google single sign-on, no passwords), the 9-step revocation runbook with edge-only emergency mode, the provisioning mirror script, the 302-to-Access health signal, and the live-verify list for every endpoint shape including the current OpenClaw inbound webhook docs at openclaw.ai (the brief separately mandates this research; the webhook design's plugin choice is validated against the live docs before wiring).

6.4 FURNACE (design/furnace-design.md). Contributes: all cost ceilings and caps (Section 4 above), the dirt-cheap smoke test with pinned balance endpoints in config/smoke-endpoints.json, the frozen-research and targeted-retry rules that bound the 3-strike loop, the runtime model tiering with deny patterns and the guard-no-anthropic-runtime.py merge gate, the one-cron inventory rule with guard-cron-inventory.py (no heartbeat entry ever, no queue poller, no per-job watchers, dashboard triggers nothing), alert dedup with the storm cap, and the churn rule that a departed client leaves zero recurring jobs. The consolidated config block in furnace-design Section 8 ships as the skill's default config, per-client overridable.

6.5 DASHBOARD (design/dashboard-design.md). Contributes: the persistence layer that the whole engine stands on (the companion document never defined a datastore; podcast-engine.db closes that), the writer contract and legal-transition matrix, idempotency via the unique client-plus-fingerprint constraint reinforcing the webhook job key, the stage taxonomy and label map, client-clean versus operator-verbose serializers, token auth with hash-only storage, the three-blade kill switch, PII retention and scrub rules, responsive and accessibility specifications, and the fourteen acceptance criteria the Fable dashboard sub-agent must satisfy. Reconciliation note for the build: the webhook design's file ledger and the dashboard design's SQLite are complementary layers of one state system; the SQLite database is the single queryable source for dashboard and kanban, the file ledger is the webhook layer's atomic claim mechanism; podcast_state.py bridges them and the build must keep them in lockstep (claim in the ledger, record in SQLite, one writer).

---

## 7. REUSE MAP: WHAT WE ALREADY OWN AND HOW IT IS USED

The engine is integration plus hardening. Each asset below is reused or fused, and the build QC gate scores reuse fidelity.

1. Skill 57 "Social Media in a Box", first-class podcast mode: prompt 17 (podcast script writer) seeds the style-engine prompt scaffolding; prompt 14 (Kie.ai cover) seeds Step 10; config/bands.json deterministic QC provers seed qc-tier1-mechanical.py's proof style; examples/golden-modes/podcast/ is the golden-fixture pattern the engine copies for its own fixtures; the PODCAST_DEFERRED graceful-skip and fail-closed cert-before-publish patterns are adopted verbatim as pipeline postures. Boundary: Skill 57 podcast mode remains the social packaging lane; the engine is canonical for full published episodes; cross-references added so they never diverge.
2. Skill 35 social-media-planner: scripts/generate_podcast_audio.sh is the production Fish render (retry loop plus ffprobe verification), near copy-paste for Step 11 with the s2.1-pro header and reference_id parameterization added. references/playbook.md section 15 is the proven Podbean publish flow via the Convert and Flow content delivery network and seeds Step 15 exactly.
3. Skill 30 fish-audio-api-reference: TTS request templates, emotion tag inventory, ffmpeg stitching guidance, and the 3,384-line voice standard operating procedure. Updated during the build with the S2.1 Pro facts (Section 3.7) so the fleet reference is current.
4. Skill 23 role-library/podcast/ (director-of-podcast, podcast-host, audio-post-producer, qc-specialist-podcast, how-to-use-this-department, suggested-roles) and role-library/audio/ (podcast-editor, podcast-producer, mastering): the professional production doctrine. The engine BINDS to these personas (Section 13); the LUFS mastering targets, four quality gates, guest handling, distribution, and key performance indicators come from here. Do not invent parallels. Note: Skill 23 itself is the AI Workforce Blueprint, NOT a Convert and Flow skill; only its role library is bound here.
5. Dept-Kit at <OPERATOR_HOME>/Downloads/Dept-Kits/podcast/: the client-facing class kit and the output-type taxonomy (Section 8). The department how-to guide is updated to present the engine through this taxonomy.
6. Live agent identity at <OPERATOR_HOME>/clawd/agents/podcast-agent/: the existing podcast agent identity the sessionKey binds to on the operator box; the fleet wiring generalizes it per client.
7. <OPERATOR_HOME>/NEW PODCAST/: the four style intake questionnaires (Counter Intuitive, Passionate, Provocative, Vulnerable), the source-of-truth wording for the intake forms and the mapper's question-order tables.
8. Skill 44 (caf workflow operations, parentKey-first build reliability), Skill 29 (413-endpoint REST catalog), the kie.ai skill set, and ffmpeg on every client box: used as-is per the designs.

---

## 8. THE FOUR OUTPUT-TYPE PRESETS

From the Dept-Kit taxonomy, fused with the companion document's two Production Modes. A preset is a named bundle of mode, pipeline scope, and deliverable set selected at intake (default derivable from mode when absent):

1. INTERVIEW (mode: interview_style_podcast). Full 18-step run. Deliverables: published episode, cover, Episode Package, Speech Script, book teaser PDF, workflow enrollment. The SHUA lead generation lane.
2. SOLO (mode: personal_podcast_style). Full run minus teaser and workflows; running spreadsheet update instead. The client's own weekly episode in their cloned voice.
3. SEASON-STRATEGY. A planning deliverable, not an episode: season arc, episode slate, style and mode per slot, drawing on the Skill 23 director-of-podcast doctrine. No render, no publish; produces an Episode Package-style strategy document only. Runs the research stage and the build gate's document QC, skips Steps 6 to 17.
4. EPISODE ASSET PACK. Regenerates or completes the asset set for an EXISTING episode (cover, documents, teaser) without re-writing or re-publishing audio; idempotent against the ledger. Useful for repairs and for Skill 57 social packaging handoffs.

Presets 3 and 4 are thin variations over the same pipeline and state machine, not separate systems; the preset field lives in the canonical payload and the ledger.

---

## 9. GAP REGISTER: EVERY KNOWN GAP AND ITS CLOSURE

| # | Gap in the source documents | Closed by |
|---|---|---|
| 1 | No persistence layer anywhere (queue, idempotency, dashboard had no home) | dashboard-design Section 5: podcast-engine.db, single writer podcast_state.py, transition matrix |
| 2 | No idempotency: upstream retries could produce duplicate episodes | webhook-design Section 3: job key, canonical hash, exclusive-create ledger claim, double-publish guard; reinforced by the SQLite unique constraint |
| 3 | No cost ceilings; 3-strike loop implied up to 3x full cost; no research cap | furnace-design Guardrails 3 and 4: hard ceilings, frozen research, targeted retries, token budgets |
| 4 | Per-client isolation asserted but not enforced; credential lookup vague | ghl-design Sections 2 and 7: alias resolver, ENV-CHECK-BEFORE-FAIL, pairing proof, fingerprint anti-commingling, ghl_credential_gate.py; webhook tenant check |
| 5 | QC self-scored by the writer (no independence) | QC-PROTOCOL-AND-MATRIX.md: deterministic Tier 1 script plus a separate cheap-tier judge model plus the qc-specialist-podcast persona distinct from the writer persona |
| 6 | Cloudflare hosting undecided; no revocation path | cloudflare-design: BlackCEO-hosted decision, 9-step revocation runbook, three-blade kill switch |
| 7 | Smoke test, pollers, and dashboard could each become a furnace | furnace-design Guardrails 1, 2, 6: balance endpoints, read-only dashboard, one-cron inventory |
| 8 | Founder alert storms (20 queued jobs = 20 messages) | furnace-design Guardrail 7: alert-dedup.py |
| 9 | Fish Audio model drift (spec says S2/S2-Pro; current is S2.1 Pro) | Section 3.7 facts; render module pins s2.1-pro via header, forbids the free tier, live-verifies at canary |
| 10 | Build brief says "version 18" against a stale v10.x snapshot | Section 3.1: live baseline v17.0.45, capstone v18.0.0, annotated tag before merge |
| 11 | "Best available GHL tool" ambiguity (MCP unusable in fan-outs) | ghl-design Section 1 tier doctrine |
| 12 | Founder-confirmation items scattered through the spec | Section 15: consolidated as onboarding INPUTS, never build blockers |

---

## 10. LOOP ENGINEERING: CONTINUOUS AND SELF-CORRECTING

Loop engineering is built into three layers:

1. THE EPISODE LOOP (runtime). Every episode is a state machine with durable state (TaskFlow plus ledger plus SQLite). Every failure has a typed handler: QC failure loops through targeted revision to the 3-strike cap; credit-out holds and resumes; rate limits full-stop and reschedule; crashes resume idempotently from the last recorded state; nothing is ever silently dropped (a delayed episode is acceptable, a lost one is not). The daily smoke test is the loop's heartbeat substitute: one bounded probe that also ages and drains the queue.
2. THE BUILD LOOP (/goal execution). Waves execute, self-QC against the 8.5 build gate, fix anything below 8.5 autonomously, re-run, and only then merge. Failed or rate-limited sub-agents are re-dispatched with state passed forward (resumeFromRunId); the loop does not stop until DONE, and DONE is merge-gated: if the repo is not updated it is not done. Progress persists to TODO.md and SESSION-LOG.md so any session can resume the loop cold.
3. THE FLEET LOOP (post-build). Canary on the operator box, hold at repo-only, validate config on every box after any future fan-out, guard-cron-inventory sweep for orphans, and the QC matrix re-runnable at any time as a regression gate. Self-correction is enforced by scripts, not prose: every guardrail is a named executable with an exit code that a gate consumes.

---

## 11. THE TWO QC GATES (SUMMARY; FULL TEXT IN QC-PROTOCOL-AND-MATRIX.md)

GATE A, BUILD/MERGE: the fleet 10-category rubric, threshold 8.5. Decides whether build work merges into the onboarding repo. Below 8.5: the execution agent fixes it and re-runs. At or above 8.5: push and merge. Never ask the founder for a green light the rubric already grants.

GATE B, EPISODE: 16 Tier 1 hard-fail checks (all binary, any single failure means not deliverable), then the 10-dimension quality rubric at 8 or higher per dimension with no averaging, then the honest per-episode checklist, with the 3-strike cap and founder notification. Decides whether an EPISODE ships to a listener.

The gates never substitute for each other and their thresholds are not interchangeable. The matrix in QC-PROTOCOL-AND-MATRIX.md maps every pipeline stage and every build deliverable to its specific checks and the script that proves them.

---

## 12. VERSIONING, TAGGING, INDEX, AND UPDATE PLAN

1. All build work happens on branches and pull requests against the live onboarding repo; the merge train is SERIAL with a single merge-writer agent (fleet doctrine; three trains collided on 7-05, never again). Command Center changes ride their own separate serial train in the command center repo.
2. Before the merge: update update.sh so the skill count includes the new skill; run hash-content-manifest.py to re-stamp _index.json content_sha for every touched skill and role file; bump the content version to v18.0.0; create the ANNOTATED tag with git tag -a v18.0.0 (a bare tag is rejected by G1); tag BEFORE merge.
3. Merge order inside the serial train: shared-resolver alias change first (smallest blast radius, restamp), then the skill directory, then role and department wiring, then docs and SOPs, then version bump and tag, then merge, then verify from a fresh clone (GitHub is the source of truth; verify via gh and a fresh clone, never via a local working copy alone).
4. Post-merge: canary the merged repo on the operator box end to end. Fleet rollout is HELD (repo-only) until the operator OK. No client box is touched in this build.
5. Repo hygiene: the repo is fleet-wide; no client names, hostnames, or identifiers anywhere in it; grep every pull request for client identifiers before merge. Never run update-skills.sh from anything but a git checkout.

---

## 13. DEPARTMENTS, ROLES, AND SOP PLAN (THE ACCESS DECISION, REASONED)

The operator asked this plan to work out which departments and roles need access to the engine and which standard operating procedures to add or update. Reasoning: access follows the pipeline's chain of custody; anything that neither executes a pipeline step nor consumes a published deliverable gets NO access, because every additional consumer is attack surface, token burn, and QC ambiguity.

DEPARTMENTS AND ROLES WITH ACCESS:

1. Podcast department (id "podcast", EXISTS on the universal floor): OWNER. The intake sessionKey binds to this department's agent. Role bindings within the pipeline: director-of-podcast owns the run end to end, the kanban card, preset selection, and the 3-strike escalation to the founder; podcast-host is the voice-and-framing persona consulted for Personal mode tone fidelity and Interview mode show framing (Steps 5 to 8); audio-post-producer owns Steps 10 to 11 (art finalization, render, stitch, LUFS mastering) plus media QC; qc-specialist-podcast owns Step 9 and MUST be a different persona from whichever persona drafted (independence rule; the judge model tier is also distinct from the writer model).
2. Audio roles (role-library/audio/): podcast-editor and mastering support audio-post-producer at Step 11 for repair passes; podcast-producer supports director-of-podcast for Season-Strategy presets. Same department floor, supporting capacity.
3. Master agent (routing doctrine): ROUTING ONLY. It dispatches inbound podcast jobs to the podcast department per the master routing doctrine and never executes pipeline steps.
4. Social media / content department: READ-ONLY, downstream. May read completed episode records and published links to feed Skill 57 social packaging (Episode Asset Pack preset is the sanctioned handoff). Zero write access to the pipeline or its state.
5. Marketing department: READ-ONLY on published links and the Episode Package for promotion planning. Nothing else.

EXPLICITLY NO ACCESS: sales, finance, legal, personal-assistant, and every other floor department (customer messaging belongs to Convert and Flow workflows, so not even the personal-assistant department may message about episodes); client-side humans interact only through the dashboard and Convert and Flow.

SOPs TO ADD (each ships as a repo document wired to the department, each with an enforcement pointer, because a standard operating procedure without a gate is a suggestion):

1. SOP Podcast Engine Runbook: the 18-step per-episode procedure, state vocabulary, failure handling. Enforced by podcast_state.py's transition matrix.
2. SOP Podcast Client Onboarding: webhook route and secret, Cloudflare provisioning, credential gate full mode, workflow discovery, Podbean podcast_id capture, running spreadsheet creation, book_teaser field reminder, T1 to T9 verification. Enforced by the provision script's gate and the T1 to T9 executable.
3. SOP Podcast Revocation and Churn: the 9-step runbook plus the three-blade kill switch. Appended to the EXISTING fleet Cloudflare revocation runbook, never a competing document. Enforced by revoke-podcast-client.sh's own verification step.
4. SOP Podcast Credit Health and Queue: daily smoke test, credit-out holds, 60-day age-out, alert dedup. Enforced by guard-cron-inventory.py and the smoke test's self-metering.
5. SOP Podcast Episode QC: the two-tier episode gate, three-pass reading, 3-strike escalation. Enforced by qc-tier1-mechanical.py and qc-attempt-gate.py.
6. SOP Book Teaser: the bonus asset procedure, fabrication boundary, PDF typography floor. Enforced by the teaser module's checks and the episode gate.

SOPs AND DOCS TO UPDATE:

1. Skill 23 role-library/podcast/how-to-use-this-department: present the engine as the department's execution engine with the four presets; keep the doctrine (gates, LUFS, KPIs) authoritative.
2. Skill 57 podcast-mode docs: add the boundary and cross-reference (engine canonical for episodes, 57 for social packaging).
3. Skill 35 references/playbook.md section 15: cross-link the engine as the productionized Podbean flow.
4. Skill 30 fish-audio-api-reference: S2.1 Pro model id, header-based selection, tag inventory, pricing and concurrency facts, free-tier prohibition.
5. Shared credential resolver used by Skills 29, 36, 44: add the CONVERTFLOW alias family; restamp every touched index hash.
6. Dept-Kit podcast how-to (client-facing): align the class kit language with the presets and the dashboard. Client-facing name: Convert and Flow.
7. department-floor.py expectations: verify the podcast department entry still passes with the new skill attached (no floor count change; the department exists).

---

## 14. PER-CLIENT CREDENTIAL NEEDS (LABELS AND LOCATIONS ONLY, NEVER VALUES)

Documented by label and expected location; verification is always SET or NOT SET plus a behavior probe; values are never printed, echoed, grepped into reports, or pasted into chat. All are the NAMED CLIENT'S OWN accounts; no operator, shared, agency, or other-client credential ever substitutes.

| Credential (label) | Purpose | Expected location |
|---|---|---|
| Fish Audio API key | Step 11 synthesis | Client env stores (all three, live process env first); Fish Audio skill set |
| Fish Audio voice reference_id | The client's own private voice model | Fish Audio skill set config; client env |
| Kie.ai API key | Step 10 cover art | Client env stores; kie.ai skill set |
| Convert and Flow private integration token (prefix pit-; identical to "API key" under any alias) | Steps 0, 14, 16, 17 | Client env stores via the 11-plus-alias resolver; openclaw.json both env shapes; auth-profiles.json |
| Convert and Flow Location ID | Tenant check and every data-plane call | Client env via its alias set; must equal the webhook payload's location_id |
| Podbean Channel ID (podcast_id) - the ONLY client-supplied Podbean value | Step 15 selects the client's show under BlackCEO's host account | Captured at onboarding into the per-client env/state; never a secret |
| Podbean app client_id + client_secret - BlackCEO's SINGLE shared app (NOT the client's) | Step 15 OAuth, injected at runtime by the n8n Podbean broker | n8n broker only; NEVER asked from the client, never required on the client box (local fallback = operator's OWN box) |
| Ollama Cloud API key OR OpenRouter API key | Content writing per the routing policy | Client env; ollama-cloud provider needs baseUrl, not apiKey slotting |
| PODCAST_INTAKE_HOOK_SECRET | Webhook route auth | Generated at onboarding (openssl rand -hex 32), client env store or 0600 secrets file |
| PODCAST_DASHBOARD_TOKEN | Dashboard data-layer defense in depth | Generated at provision, client env stores |
| CLOUDFLARE_API_TOKEN (BlackCEO's own) | Provision and revocation, operator side only | Operator secret stores; never on client boxes; never trust CLOUDFLARE_ZONE_ID |

Funding note: Kie.ai, Ollama Cloud or OpenRouter, and Fish Audio bill per use; the daily smoke test proves funded reachability before work depends on it.

---

## 15. FOUNDER CONFIRMATIONS: ONBOARDING INPUTS, NOT BUILD BLOCKERS

The companion document's build-handoff questions are honest unknowns that vary per client. The build treats every one of them as a per-client onboarding INPUT with a defined capture step and a safe failure mode, so none of them blocks the build itself:

1. Exact Convert and Flow workflow names and trigger mechanisms (06-Podcast_Episode_Is_Ready, 04-Podcast is Completed): discovered per client at setup via Skill 44 listing; missing workflow stops SETUP for that client with a founder surface, never guessed, never auto-built at runtime.
2. Per-client Podbean Channel ID (podcast_id): captured at onboarding; the payload requires it and the mapper refuses to guess it. This is the ONLY Podbean value the client supplies (it selects their show under BlackCEO's single host account) and it is not a secret. The Podbean OAuth app client_id/client_secret are BlackCEO's single shared app, injected at runtime by the n8n Podbean broker, never asked from the client.
3. Snapshot custom fields: verified by the Step 0 smoke test; missing fields route the client to support; never silently created.
4. book_teaser custom field: may not exist; surfaced as a founder reminder at setup and noted in delivery reports; never fails an episode, never silently created.
5. Notification timing inside the workflows, the Personal running spreadsheet, the Notion parent page where applicable, the client's document tooling, the client's web research tool, and reachable models: all captured by the onboarding runbook's checklist with detect-first logic and recorded in the per-client state file.

---

## 16. RISKS AND MITIGATIONS

1. Endpoint drift (Cloudflare, OpenClaw webhook schema, Fish header enum, Podbean): every design marks LIVE-VERIFY items; wave 0 verifies them against live docs before any wiring; nothing ships on fleet memory alone.
2. Merge-train collision: single merge-writer, serial train, annotated tag before merge, fresh-clone verification.
3. Rate-limit trip from fan-out: stagger under roughly 20 concurrent, resumeFromRunId, never stack trains.
4. Anthropic leakage into runtime: guard-no-anthropic-runtime.py at the merge gate plus runtime deny patterns.
5. Client-facing leakage: silence doctrine in every script; no client Telegram sends anywhere in the engine; qc-completeness.sh never run standalone.
6. Cross-client contamination: physical isolation plus tenant check plus PIT fingerprint plus per-client secrets; structurally impossible rather than policed.
7. False done: independent verification gates at every layer (T1 to T9 executed and observed, read-back verification, 302-to-Access probes, fresh-clone check, canary end to end); a sub-agent's claim is a hypothesis until independently verified.

---

## 17. SUCCESS CRITERIA (DEFINITION OF DONE)

The build is DONE only when every item in CHECKLIST.md Part C passes, and in summary: the skill is built, wired, and MERGED at v18.0.0 with an annotated pre-merge tag; update.sh skill count correct; _index.json content_sha restamped; the podcast department wiring, persona matching, kanban pickup, and both QC gates proven working; the dashboard built to its fourteen acceptance criteria with Cloudflare hosting and revocation wired; all guardrail scripts present and passing; the PRD folder present in the onboarding master files at project-prds/podcast-engine/; the entire flow proven end to end on the operator box (canary) with a test submission through the REAL public URL; fleet rollout HELD at repo-only; zero client-facing messages emitted anywhere; zero secrets printed anywhere; zero Anthropic references in shipped runtime. If the repo is not updated, it is not done.
