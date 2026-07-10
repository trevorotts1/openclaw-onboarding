# SOP-PODCAST-01: PODCAST ENGINE RUNBOOK (the 18-step per-episode procedure)

**Cluster:** Podcast-Craft Rules (`universal-sops/podcast-craft/`)
**Master authority:** `58-podcast-production-engine/SKILL.md` + `project-prds/podcast-engine/PRD.md` Section 5 (the canonical 18-step pipeline) + `project-prds/podcast-engine/design/dashboard-design.md` Section 5 (persistence and the legal-transition matrix)
**Owning role:** Director of Podcast (`director-of-podcast`) owns the run end to end, the kanban card, preset selection, and the three-strike escalation. Quality Control at Step 9 is owned by `qc-specialist-podcast`, who MUST be a different persona from whichever persona drafted (independence rule).
**Enforcement pointer (binding):** `58-podcast-production-engine/scripts/podcast_state.py` is the SOLE writer of the engine state and the owner of the legal-transition matrix. Every stage change in this runbook is recorded through this writer and no other; an illegal transition raises `TransitionError` and exits 3, a write for a churned client exits 4, so a step that skips the matrix cannot advance the job. Cost is metered by `58-podcast-production-engine/scripts/podcast-cost-ledger.py`; the episode Quality Control gate is proven by `58-podcast-production-engine/scripts/qc-tier1-mechanical.py` (deterministic Tier 1) and `58-podcast-production-engine/scripts/qc-attempt-gate.py` (attempt counter and three-strike cap). A stage without a recorded, legal transition is not done.
**Stage:** Step 0 once per client (first-run smoke test), then Steps 1 to 18 once per episode.

---

## 0. WHY THIS SOP EXISTS, AND THE ONE LAW

An episode is a durable state machine, not a single conversation. The one law: every state change passes through `podcast_state.py`. The dashboard, the kanban board, the credit-out queue, and the cost ledger all READ that one state; nothing recomputes it. A delayed episode is acceptable; a lost or duplicated episode is not. This SOP is the human-readable face of the transition matrix the writer enforces in code.

Two writing rules bind every byte this engine produces and are Tier 1 hard-fail checks at Step 9: zero em dash characters anywhere in a deliverable, and no triple-backtick or code-fence markers of any kind in a produced script, JSON, or document output.

## 1. STATE VOCABULARY (two reconciled layers plus the client label map)

The engine keeps ONE state system in two complementary layers that `podcast_state.py` bridges in lockstep: the webhook layer's file ledger (the atomic claim) and the SQLite database `~/.openclaw/podcast-engine/podcast-engine.db` (the single queryable source for dashboard and kanban).

The SQLite `status` enum is canonical and is what the transition matrix enforces:

    received -> researching -> writing -> in_qc -> generating_art
      -> producing_audio -> publishing -> enrolling -> complete

Holding and terminal states sit outside that linear path: `queued_credit_out` (hold), `failed` (terminal), and `complete` (terminal). The `queue_state` column carries `none | held | resumed | aged_out`; the credit-out service that caused a hold is one of `kie_ai | ollama_cloud | openrouter | fish_audio`.

The intake ledger uses short names for three stages so the webhook layer and the pipeline agree without a rename: `in_qc` maps to ledger `qc`, `generating_art` to `art`, `producing_audio` to `audio`; every other name matches. The webhook layer additionally owns `received`, `needs_input`, `test`, and the `duplicate` accounting; the pipeline owns the rest.

Client-facing labels (the ONLY status words a client ever sees, served by the dashboard's client-clean serializer): received = Received, researching = Researching, writing = Writing, in_qc = Quality review, generating_art = Creating artwork, producing_audio = Producing audio, publishing = Publishing, enrolling = Finalizing, complete = Live, queued_credit_out = On hold, failed = Needs attention. Operator-verbose views may show the raw enum; client views never do.

## 2. THE LEGAL-TRANSITION MATRIX (exactly as the writer enforces it)

`podcast_state.py check_transition` permits only these moves; everything else raises and exits 3:

1. Forward adjacency along the linear order above, one step at a time (use the `advance` subcommand).
2. The Quality Control revision loop: `in_qc -> writing`, permitted only while `attempt_count < 3`. At three, the only legal exit from `in_qc` is `failed`.
3. Any non-terminal stage may go to `queued_credit_out` (use `hold`, never `advance`).
4. Leaving a hold: `queued_credit_out` may move ONLY to the recorded `resume_stage` (use `resume`), or to `failed` (aged out or unrecoverable).
5. Any stage may go to `failed` on an unrecoverable error or the three-strike cap.
6. `complete` and `failed` are terminal; re-dispatch happens through the engine, never by re-writing a terminal row.
7. The writer refuses ALL new state changes for a client whose `podcast_client_state.active = 0` (churn); this exits 4 and is the engine kill-blade referenced by SOP-PODCAST-03.

Writer subcommands and their exit codes: `create` (idempotent job creation from the intake payload), `advance`, `output` (set an output column such as a permalink or a document link), `hold`, `resume`, `fail`, `sweep-aged-out` (drop holds past the 60-day maximum), `scrub-pii`, `deactivate-client`, `token`, `get` (read-only), `init`. Exit codes: 0 pass, 1 error, 2 usage, 3 illegal transition, 4 writer refused (churned client).

## 3. THE 18 STEPS, EACH MAPPED TO A STATE AND A WRITER CALL

Step 0 (once per client, not per episode): first-run smoke test. Run `ghl_credential_gate.py` in full mode (see SOP-PODCAST-02). Confirm the custom field map keys exist exactly, including the double underscore in `podcast_survey__additional_info`; confirm the client's OWN private integration token and Location ID pair-prove against the Location; confirm the n8n Podbean broker is reachable (or, on the operator's own box, the shared Podbean app credentials are present) and the client's Podbean Channel ID (podcast_id) is captured, and confirm Fish Audio and Kie.ai credentials are present. The Podbean OAuth app client_id/client_secret are BlackCEO's single shared app, injected by the broker, and are NEVER asked from the client. Missing custom fields: STOP and route the client to support for the snapshot; never create fields silently.

1. INGEST. Read every survey answer through the custom field map, honoring `contact.my_preferred_pronoun` for every reference. State: `received` (the webhook layer created the job via `create`).
2. SELECT ENGINES. Load the matching Style Engine (Counter Intuitive, Vulnerable, Provocative, or Passionate) and Mode (Personal or Interview). No state change; still `received`.
3. RESEARCH ASSISTANT STAGE. Improve and expand every answer without changing intent, extract three power statements, generate missing takeaways, research up to three REAL verified case studies. Capped at 12 web calls (metered by the cost ledger). The package is FROZEN after this step; Quality Control retries reuse it. `advance` to `researching`.
4. SIZE. Choose a 7 to 15 minute runtime at 140 words per minute; 10 minutes (about 1,400 spoken words) is the default. Thin material means a tight short episode, never padding.
5. BLUEPRINT. Title (immutable after this step, never preceded by the word Title), one-sentence thesis, the style signature line verbatim, every arc beat with a word budget, transparency beat placement, opening and final lines written first. Internal only. `advance` to `writing`.
6. DRAFT. Full script in Final Draft format: prose only, everything speakable, numbers and symbols written as spoken, Fish Audio square-bracket tags embedded (one tag roughly every two to five sentences, concentrated at pivots). Still `writing`.
7. IMPROVEMENT PASS. More compelling and more emotionally captivating, tone enforced in every paragraph; forbidden from changing the title or thesis, removing the transparency beat, adding fabricated material, or inflating length.
8. READ-ALOUD PASS. Fix anything a mouth would stumble on at speaking pace.
9. QUALITY CONTROL (the episode gate, distinct from the build gate). `advance` to `in_qc`. Run all 16 Tier 1 hard-fail checks via `qc-tier1-mechanical.py` at zero model cost; the semantic checks (fabrication, mode perspective, pronoun correctness) and the 10-dimension rubric run on the cheap judge tier (Gemini 3.1 Flash Lite or GLM 5.2), never on the writer model. `qc-attempt-gate.py` owns the counter: on failure, targeted revision (`in_qc -> writing`) reusing the frozen research; a hard stop at three failures moves the job to `failed` with a founder notification carrying the failing checks and the best draft, routed through `alert-dedup.py`. Full detail: SOP-PODCAST-05.
10. COVER ART. Kie.ai GPT-image-2 at 1K square from the visual description anchored by the theme and title, then ffmpeg in house: square, 1400 to 3000, JPEG, RGB, under 512 kilobytes, spec-valid filename, never below 1400 square. `advance` to `generating_art`.
11. AUDIO. Fish Audio model `s2.1-pro` (selected via HTTP header) with the client's OWN `reference_id`, mp3 at 192; the free tier `s2.1-pro-free` is structurally refused for client content. Split at natural beat boundaries if a per-request limit demands (never mid-sentence, never mid-tag), `condition_on_previous_chunks` true, ffmpeg-join seamlessly, master to the department loudness doctrine (minus 14 to minus 16 LUFS integrated), verify with ffprobe. `advance` to `producing_audio`.
12. DOCUMENTS. Detect tooling (Google preferred, then Notion, then plain text). Episode Package rich and fully rendered (no font below 12 point); Speech Script clean text only. Google sharing: anyone with the link can edit.
13. BOOK TEASER (Interview mode ONLY; Personal mode skips entirely). First-chapter book intro, at most three pages, in the person's own voice, cliffhanger ending, built only from what they shared plus verified research, written on Kimi 2.6 or GLM 5.2, rendered as a book-typeset PDF with no font below 14 point. Full detail: SOP-PODCAST-06.
14. STORE MEDIA. Tier 3 REST upload (Skill 29) of MP3, cover, and teaser PDF into the client's Convert and Flow media library folders (create-once, reuse-forever, case-insensitive matching); HEAD-verify every returned public URL. `advance` to `publishing`.
15. PUBLISH TO PODBEAN. OAuth using BlackCEO's SINGLE Podbean app, injected at runtime by the n8n Podbean broker (never the client's, never asked, never required on the client box; a local client_credentials mint is a fallback only on the operator's own box), scoped to the client's Podbean Channel ID (podcast_id, the only Podbean value the client supplies); episode number is count plus one; the title convention appends "Inspired by" plus the speaker's name; uploadAuthorize then PUT for audio and image; create the episode (publish now, or draft or scheduled when a future release date exists); capture the permalink. Idempotent: if the ledger already holds a permalink, skip. Record the permalink with `output`.
16. LINK BACK. Write title, description, Episode Package link, and Speech Script link (and `book_teaser` when the field exists) in one batch, then write `contact.podcast_survey_episode_url` ALONE and LAST because it is a live customer-facing trigger for workflow 04. Read back every field byte-for-byte; a mismatch retries once, then enters failure handling.
17. TRIGGER AND ENROLL (mode-dependent). Interview: verify whether the URL write already field-triggered 04-Podcast is Completed, enroll explicitly only if not, enroll 06-Podcast_Episode_Is_Ready per the discovered trigger, verify both via `caf` reads. Personal: append the episode row to the running spreadsheet, no workflows, no messages. The enrollment function hard-refuses `personal_podcast_style`. `advance` to `enrolling`.
18. DELIVER. The deliverable is the pure script plus links; the delivery report (title, honest word count, runtime, style, mode, writing model including any substitution, research tool, document destinations and links, media locations, Podbean link, Convert and Flow save confirmations, enrollment confirmation, image prompt, completed checklist, rubric scores) goes to the OPERATOR channel only, never inside the script, never to the customer. `advance` to `complete`.

## 4. FAILURE HANDLING (every failure has a typed handler; nothing is silently dropped)

- Quality Control failure: targeted revision loop `in_qc -> writing` capped at three by `qc-attempt-gate.py`, then `fail`.
- Credits out mid-run: any insufficient-credits error moves the job to `queued_credit_out` with the full payload and partial state recorded (`hold`), a 60-day maximum, a daily age-check (`sweep-aged-out`), and `resume` to the recorded `resume_stage`.
- Rate limit (Convert and Flow 429): full stop, read `Retry-After`, schedule exactly one resume; a second consecutive 429 holds the job and alerts the founder. Never tier-hop on a 429 (all tiers share one bucket).
- Cost ceiling trip: the cost ledger enforces soft 2.50 and hard 5.00 per episode, 15.00 per client per day, 3 episodes per client per day, 400,000 content tokens per episode; a hard trip holds the job (`cost_hold` semantics via `queued_credit_out`) and alerts the founder.
- Crash mid-production: the durable TaskFlow plus the ledger resume the job idempotently from the last recorded state; publish, link-back, and enrollment are individually idempotent (permalink check before publish, field-equality check before write, enrolling-before-complete states).
- Every alert routes through `alert-dedup.py` to the founder only (one alert per client-service-failure class per 6-hour window, storm cap then digest).

## 5. TWO HARD BOUNDARIES

- MCP-free pipeline: sub-agents get NO Model Context Protocol injection. Every tool-bearing step (Convert and Flow media upload, custom field writes, Skill 44 enrollment, Podbean) executes in the podcast agent's OWN turn. Sub-agents handle pure content work only (research synthesis, drafting, improvement, Quality Control reads). The Convert and Flow data plane is Skill 44 `caf` (Tier 0) first and Skill 29 direct REST (Tier 3) second, mandatory for binary media uploads; the two MCP tiers are structurally forbidden here.
- Silence: this runbook emits zero client-facing messages. The engine STOPS at Step 17; Convert and Flow owns all customer messaging. Operator alerts go to the founder channel only.

## 6. RUNTIME MODEL ROUTING (no Anthropic ever ships in runtime)

All content work routes to Ollama Cloud Kimi 2.6 first, then GLM 5.2 (thinking high), then the OpenRouter equivalents in the same order, then Gemini 3.1 Flash Lite as the final fallback. No Anthropic model id, provider, package, key, or host appears in any runtime file; `guard-no-anthropic-runtime.py` enforces this at the merge gate and refuses deny-pattern substitutions at runtime. The judge tier used at Step 9 is always distinct from the writer tier.

## 7. DEFINITION OF DONE FOR ONE EPISODE

The episode is deliverable only when all 16 Tier 1 checks pass, all 10 rubric dimensions score 8 or higher with no averaging, the per-episode checklist (`project-prds/podcast-engine/CHECKLIST.md` Part A) is honestly complete, the media and permalink and field read-backs all verified, and the job has reached `complete` through legal transitions recorded by `podcast_state.py`. Anything less is not delivered.
