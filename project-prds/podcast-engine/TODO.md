# TODO, PODCAST PRODUCTION ENGINE BUILD (LIVE TASK LIST)
### Every execution agent appends its progress here: task id, agent name, status, timestamp, branch, pull request, gate score.
### Status vocabulary: PENDING / IN-PROGRESS / BLOCKED(reason) / GATE-FAIL(score) / DONE(verified-by).
### Cap: about 100 Opus 4.8 execution sub-agents total, STAGGERED at 15 to 20 concurrent, plus ONE Fable sub-agent for the dashboard (W3.1). Re-dispatch on failure or rate limit with resumeFromRunId; never stop the loop.

## WAVE 0: PREFLIGHT AND LIVE VERIFICATION (8 Opus 4.8 agents; W0.1 first, rest parallel)
- [ ] W0.1 Repo baseline snapshot (version, gates, update.sh count, _index.json, department-floor podcast entry, project-prds location). PENDING
- [ ] W0.2 LIVE-VERIFY OpenClaw Webhooks plugin schema against the installed gateway version. PENDING
- [ ] W0.3 LIVE-VERIFY Fish Audio s2.1-pro header on POST /v1/tts; voices and clone endpoints; pin facts. PENDING
- [ ] W0.4 LIVE-VERIFY Cloudflare API shapes (Access, tunnel config, DNS, WAF, plan tier). PENDING
- [ ] W0.5 LIVE-VERIFY Podbean API and Skill 29 folder-create endpoint. PENDING
- [ ] W0.6 Reuse-asset inventory pinned (Skills 57/35/30/23, Dept-Kit, NEW PODCAST, podcast-agent). PENDING
- [ ] W0.7 Balance-endpoint discovery for smoke-endpoints.json. PENDING
- [ ] W0.8 PRD folder copied into onboarding branch at master-files project-prds/podcast-engine/. PENDING

## WAVE 1: CORE SKILL AUTHORING (28 Opus 4.8 agents, two staggered batches of 14)
- [ ] W1.1 SKILL.md runbook (18 steps, presets, boundaries, silence). PENDING
- [ ] W1.2 Style Engine: Counter Intuitive. PENDING
- [ ] W1.3 Style Engine: Vulnerable. PENDING
- [ ] W1.4 Style Engine: Provocative. PENDING
- [ ] W1.5 Style Engine: Passionate. PENDING
- [ ] W1.6 Mode module: Personal Podcast. PENDING
- [ ] W1.7 Mode module: Interview Style. PENDING
- [ ] W1.8 Research Assistant module (freeze, caps, case-study rules). PENDING
- [ ] W1.9 Blueprint and sizing module. PENDING
- [ ] W1.10 Tagging module (S2.1 Pro palette, S1 conversion). PENDING
- [ ] W1.11 Fish render module (adapt Skill 35 script; s2.1-pro; reference_id; LUFS; ffprobe). PENDING
- [ ] W1.12 Image module (Kie.ai GPT-image-2; ffmpeg finalize; poll bounds). PENDING
- [ ] W1.13 Documents module (detect-then-create; Package rich; Script clean). PENDING
- [ ] W1.14 Book teaser module (3 pages; 14-point floor; fabrication boundary; PDF). PENDING
- [ ] W1.15 Podbean publish module (playbook section 15 base; idempotent permalink). PENDING
- [ ] W1.16 Webhook layer (route, mapper, job key, ledger, flow trigger, 409, quarantine). PENDING
- [ ] W1.17 Webhook fixtures and unit tests (three upstream families). PENDING
- [ ] W1.18 Convert and Flow field layer (shared-resolver CONVERTFLOW aliases; URL last; read-back). PENDING
- [ ] W1.19 Media upload layer (Tier 3 multipart; folders; HEAD verify). PENDING
- [ ] W1.20 Enrollment layer (Skill 44 discovery; verify-then-enroll; Personal refusal; spreadsheet). PENDING
- [ ] W1.21 Config set (furnace config, model routing with deny patterns, smoke-endpoints, cost-model). PENDING
- [x] W1.22 Golden fixtures (both modes plus Season-Strategy plus Asset Pack). DONE on branch feat/podcast-golden-fixtures; 46 files at 58-podcast-production-engine/examples/golden-modes/podcast/; both episodes pass 16 Tier 1 checks and 10-dim rubric floor of 8; self-verifier verify-fixtures.py green; zero em dashes, zero fences, zero Anthropic model refs.
- [ ] W1.23 Preset layer (4 output types over the pipeline scope map). PENDING
- [x] W1.24 Intake questionnaire wiring (NEW PODCAST question order tables). DONE (branch feat/podcast-intake-questionnaires-and-payload; self-QC 9.3; pending W6 merge)
- [x] W1.25 Canonical payload module. DONE (branch feat/podcast-intake-questionnaires-and-payload; self-QC 9.3; pending W6 merge)
- [ ] W1.26 Delivery report generator (operator channel only). PENDING
- [ ] W1.27 Credit-out queue mechanics (hold, resume, 60-day age-out). PENDING
- [ ] W1.28 Personal running spreadsheet logic. PENDING

## WAVE 2: GUARDRAIL SUITE (12 Opus 4.8 agents, parallel)
- [ ] W2.1 podcast_state.py (sole writer, transition matrix, redaction). PENDING
- [x] W2.2 podcast-cost-ledger.py (ceilings, caps, budgets). DONE(self-test 11/11; branch feat/podcast-cost-and-metering)
- [x] W2.3 podcast-smoke-test.py (at or under 1 cent; queue age check). DONE(self-test 9/9; branch feat/podcast-cost-and-metering)
- [ ] W2.4 qc-tier1-mechanical.py (deterministic Tier 1). PENDING
- [ ] W2.5 qc-attempt-gate.py (3-strike, targeted retries, frozen research). PENDING
- [ ] W2.6 alert-dedup.py (windows, storm cap, gateway-only path). PENDING
- [x] W2.7 ghl_credential_gate.py (resolver, pairing, fingerprint, fields, rate floor). DONE(feat/podcast-credential-gate; offline battery 9/9; live pairing proven at W5 canary)
- [ ] W2.8 guard-no-anthropic-runtime.py (shipped-file scan plus routing assertions). PENDING
- [ ] W2.9 guard-cron-inventory.py (one cron, no heartbeat, churn sweep). PENDING
- [ ] W2.10 provision-podcast-client.sh (with pass gate). PENDING
- [ ] W2.11 revoke-podcast-client.sh (9 steps, edge-only mode, verification). PENDING
- [ ] W2.12 T1 to T9 verification script (executable, observed). PENDING

## WAVE 3: DASHBOARD (1 FABLE sub-agent; starts after W2.1)
- [x] W3.1 Fable dashboard build per design/dashboard-design.md, all fourteen acceptance criteria; command center repo serial train. DONE(built additively at 58-podcast-production-engine/command-center/ on branch feat/podcast-client-dashboard; verified on the operator box: tsc clean, next build green with all six /podcast routes, 7/7 serializer unit tests, 13/13 headless browser smoke checks including 375/768/1280 no-horizontal-scroll, 6/6 revocation and kill-switch drills against a podcast_state.py-seeded database; self-QC 8.7)

## WAVE 4: WIRING, ROLES, SOPS, DOCS (14 Opus 4.8 agents, parallel)
- [ ] W4.1 Department wiring into the EXISTING podcast department (no duplicate; floor passes). PENDING
- [ ] W4.2 Persona matching to Skill 23 podcast and audio roles (QC independence wired). PENDING
- [ ] W4.3 Kanban wiring (state enum to columns; lifecycle proof plan). PENDING
- [ ] W4.4 SOP: Podcast Engine Runbook. PENDING
- [ ] W4.5 SOP: Podcast Client Onboarding. PENDING
- [ ] W4.6 SOP: Podcast Revocation and Churn (append to fleet runbook). PENDING
- [ ] W4.7 SOP: Podcast Credit Health and Queue. PENDING
- [ ] W4.8 SOP: Podcast Episode QC. PENDING
- [ ] W4.9 SOP: Book Teaser. PENDING
- [ ] W4.10 Doc updates: Skill 23 how-to plus Dept-Kit client how-to. PENDING
- [ ] W4.11 Doc updates: Skill 57 boundary plus Skill 35 playbook cross-links. PENDING
- [ ] W4.12 Doc update: Skill 30 Fish reference to S2.1 Pro facts. PENDING
- [x] W4.13 Fleet Cloudflare revocation runbook: podcast blades appended. DONE(branch feat/podcast-fleet-cf-revocation-and-routing; awaiting W6 merge verify)
- [x] W4.14 Master agent routing rule for inbound podcast jobs. DONE(branch feat/podcast-fleet-cf-revocation-and-routing; awaiting W6 merge verify)

## WAVE 5: CANARY ON THE OPERATOR BOX (8 Opus 4.8 agents, serial drills)
- [ ] W5.1 Branch build installed on operator box. PENDING
- [ ] W5.2 Operator box provisioned as synthetic client. PENDING
- [ ] W5.3 T1 to T9 executed and observed, including T9 via real public URL. PENDING
- [ ] W5.4 Golden-fixture episode end to end (test contact, _test-gated), dashboard and kanban verified. PENDING
- [ ] W5.5 Force-failure drills (Tier 1, rubric, 3-strike, credit-out, cost ceiling, duplicate, wrong tenant). PENDING
- [ ] W5.6 Gate battery (anthropic guard, cron inventory, credential gate, silence and secrecy audit, repo grep). PENDING
- [ ] W5.7 Gate A scoring of every unit; sub-8.5 loops fixed autonomously. PENDING
- [ ] W5.8 Revocation drill on the synthetic client, then re-provision. PENDING

## WAVE 6: SERIAL MERGE TRAIN (1 merge-writer agent; strictly serial)
- [ ] W6.1 Shared-resolver aliases merged plus restamp. PENDING
- [ ] W6.2 Skill directory merged. PENDING
- [ ] W6.3 Wiring merged. PENDING
- [ ] W6.4 SOPs and docs merged. PENDING
- [ ] W6.5 PRD folder synced at project-prds/podcast-engine/. PENDING
- [ ] W6.6 update.sh skill count corrected. PENDING
- [ ] W6.7 _index.json content_sha restamped (hash-content-manifest.py). PENDING
- [ ] W6.8 Version bumped to v18.0.0. PENDING
- [ ] W6.9 ANNOTATED tag v18.0.0 created BEFORE merge. PENDING
- [ ] W6.10 Merge complete; fresh-clone verification passed. PENDING

## WAVE 7: POST-MERGE CANARY AND HOLD (2 Opus 4.8 agents, serial)
- [ ] W7.1 Merged-repo canary re-run (W5.3 to W5.6 from the merged artifact). PENDING
- [ ] W7.2 HOLD recorded (fleet rollout repo-only); final operator report; onboarding-inputs list surfaced; memory synced. PENDING

---

## AGENT PROGRESS LOG (append below this line; never edit rows above, only flip their status)
| Timestamp | Task | Agent | Status | Branch/PR | Gate score | Notes |
|---|---|---|---|---|---|---|
| 2026-07-06 | W2.6 alert-dedup.py (furnace Guardrail 7) | Opus exec (alert-dedup slice) | DONE, branch pushed | feat/podcast-alert-dedup | self 9.2 | scripts/alert-dedup.py plus stdlib unit tests (17 green); keys client+service+failure_class, 6h dedup window, 4/day storm cap to digest, decision-class always-send with per-episode dedup, recovery, daily flush; sole founder path via openclaw message send gateway, never client; no Anthropic, no em dash, no triple backtick (clean scan) |
| 2026-07-06 | W1.12 Cover finalize (Step 10) + W1.13 Documents (Step 12) | Opus asset-production | DONE on branch (awaiting serial merge) | feat/podcast-asset-production | self 9.0 | scripts/generate_cover.sh + scripts/render_documents.py + modules/documents.md; ffmpeg finalize and renderer proven locally |
| 2026-07-06 | W1.14 Book teaser module | Opus 4.8 (book-teaser slice) | DONE(self-verified) | feat/podcast-book-teaser | 9.0 | modules/book-teaser.md + scripts/render_book_teaser.py (deterministic, 0 model, 0 net, 0 MCP). Interview-only; 3-page cap + 14pt floor verified from the rendered PDF (pymupdf), weasyprint-preferred/Chrome-fallback, Skill 35 retry posture + Skill 53 print-CSS reuse. Self-test PASS (3 pages, 15pt) and all 4 failure modes block (em dash, page cap, sub-14pt CSS, toolchain-absent). No Anthropic ids/providers/hosts/imports/env keys; no literal em dash in source; no triple backtick fences. |
| 2026-07-06 | W2.10 + W2.11 | Opus exec (cloudflare-provision-revoke) | DONE(self-verified) | feat/podcast-cloudflare-provision-revoke | 9.0 | provision + revoke scripts under 58-podcast-production-engine/scripts/. Every Cloudflare endpoint shape LIVE-VERIFIED at developers.cloudflare.com. Zone resolved by name with wrong-zone refusal (never CLOUDFLARE_ZONE_ID). Shared zone WAF ruleset and tunnel ingress MERGED by ref, never clobbered (jq unit-tested for reuse/create/idempotency/other-client-preservation). Edge-only emergency mode + 9-step verify (edge dark, hook dead, CF clean, gateway healthy). Secrets SET-only never printed; config writes as node user never root; zero client-facing messages. shellcheck clean; no anthropic/em-dash/fences. Box-side helpers invoked-when-present else PENDING (sibling slices). |
| 2026-07-06 | W1.21 Config set | Opus 4.8 exec | DONE (branch) | feat/podcast-config-set | 9.3 self | 58-podcast-production-engine/config/{furnace,models,smoke-endpoints,cost-model,bands}.json. Routing Kimi 2.6 to GLM 5.2 to OpenRouter eq to Gemini 3.1 Flash Lite; deny_patterns; zero Anthropic usage. Ceilings 2.50/5.00/15.00, 3 ep/day, 400k tok/ep, 8k out/call. Endpoints pinned (OpenRouter GET /api/v1/key verified; Ollama Cloud no-balance so capped-turn; Kie /chat/credit; Fish wallet/self/api-credit). bands.json seeded from Skill 57. 41/41 self-QC pass. |
| 2026-07-06 | W1.8, W1.9, W1.10 | Opus 4.8 (content-authoring-modules) | DONE(self-verified) | feat/podcast-content-authoring-modules | A self-QC 9.2 | Added 58-podcast-production-engine/modules/research-assistant.md (Step 3: improve+expand answers, 3 power statements, up to 3 verified case studies, 12-call cap, package frozen), blueprint-sizing.md (Steps 4 to 5: 140 wpm table, 10-min default, immutable title, one-sentence thesis, verbatim signature line, per-style arc word budgets summing to total), tagging.md (Step 6: S2.1 Pro square-bracket palette, 1 tag per 2 to 5 sentences, mandatory locations, S1 parentheses conversion table). Zero em dashes, zero fabrication, zero Anthropic model ids. Additive slice; shared files (update.sh count, _index.json, version) untouched. |
| 2026-07-06 | W1.18 (field-layer portion) | Opus 4.8 exec | IN-PROGRESS (branch pushed) | feat/podcast-convert-and-flow-field-layer | self-QC 9.0 | Convert and Flow field layer at 58-podcast-production-engine/scripts/caf/field_layer/: resolver (ENV-CHECK-BEFORE-FAIL, PIT plus Location, agency-PIT excluded, secrecy), field-map cache with double-underscore assertion and book_teaser presence, batch-then-URL-last writer with byte-for-byte read-back and one-retry, Tier 0 caf plus Tier 3 REST only (no MCP). 35 offline tests pass. Finding: caf contacts update carries no custom-field option, so custom-field writes escalate Tier 0 to Tier 3 per command-unsupported rule. Shared-resolver CONVERTFLOW aliases remain a separate slice; field layer names the set locally meanwhile. |
| 2026-07-06 | W2.2 + W2.3 | Opus exec (cost-and-metering slice) | DONE | feat/podcast-cost-and-metering | self-QC 9.0 | podcast-cost-ledger.py (Guardrails 3+4: precheck/record/summary/grant-research-bonus, per-episode and daily ceilings, 3-episode daily cap, 400k token budget, 8k output cap, 12-call research cap plus 4-call fabrication bonus, typed CostCeilingExceeded exit codes) and podcast-smoke-test.py (Guardrails 1+6: pinned balance-endpoint probes only, never a model turn, self-metered overspend canary, queue age-out at 60 days plus drain trigger, alert-dedup spool handoff). Self-tests 11/11 and 9/9. No banned model ids, no em dash, no fences, no secrets printed, no client names. |
| 2026-07-06 | W2.7 ghl_credential_gate.py | Opus exec (credential-gate) | DONE(offline battery 9/9; live pairing at W5) | feat/podcast-credential-gate | self-QC 9.0 | 16-alias Location-PIT resolver (live env first, all stores), pit- shape (length only), pairing proof, sha256[:12] fingerprint + registry commingling, required fields incl double-underscore, rate floor; exit 0/2/3/4/5; secrecy wrapper; stdlib-only; shared files untouched |
| 2026-07-06 | W1.26 + W1.27 + W1.28 | Opus (delivery-and-queue) | DONE(self-verified: 45 pytest pass, CLIs smoke-tested) | feat/podcast-delivery-and-queue | self-QC 9.0 | scripts/delivery_report.py (operator-only report, reproduces CHECKLIST Part A honestly, refuses client destinations), credit_queue.py (hold with full payload+partial state, daily age-check, 60-day age-out+payload purge, resume from resume_stage; delegates writes to podcast_state.py, alerts to alert-dedup.py, no cron), personal_spreadsheet.py (create-at-setup idempotent, append-per-episode, custom-field link storage, Interview hard-refusal). Additive only; shared files untouched. Glyph-clean (no em dash/fence), no Anthropic tokens, no client names. |
| 2026-07-06 | W4.1+W4.2+W4.3 department-persona-kanban-wiring | Opus 4.8 exec | DONE(self-verified; W5.4 canary pending) | feat/podcast-department-persona-kanban-wiring | 9.0 | Skill 58 wired into EXISTING podcast dept via skill-department-map.json (no duplicate); sessionKey podcast:intake:<slug> bound to dept agent; 4 podcast owners + 3 audio supporters bound with QC independence (qc-specialist-podcast never drafts); ledger/DB state enum mapped 1:1 to kanban columns + card-lifecycle proof plan. department-floor.py rc0, floor unchanged at 28, podcast universal-primary. New: 23-ai-workforce-blueprint/department-wiring/podcast-engine/ (README, wiring.json, proof plan, verify-podcast-engine-wiring.py rc0). check-skill-department-map.py green except expected skill-58 disk-coverage line (resolves when W1.1 skill dir co-lands in merge train). Did NOT restamp _index.json / touch update.sh / version (merge phase). |
| 2026-07-06 | W4.1+W4.2+W4.3 department-persona-kanban-wiring (verify+access-matrix pass) | Opus 4.8 exec | DONE(self-verified; W5.4 canary pending) | feat/podcast-department-persona-kanban-wiring | 9.2 | Independently re-verified prior wiring in a fresh isolated clone (shared scratch clone was racing another slice): department-floor.py rc0 floor=28 podcast universal-primary UNCHANGED; verify-podcast-engine-wiring.py rc0; role slugs all resolve (no orphans); kanban 1:1 vs authoritative dashboard-design.md status CHECK enum (received..complete + queued_credit_out + failed + aged_out overlay). ADDED (additive, slice files only): PRD Section 13 access_matrix in wiring.json (owner=podcast write, supporting=audio write, routing_only=master-orchestrator no-write/no-steps, read_only_downstream=social-media+marketing, default-deny no_access) plus a matching enforcement assertion in verify-podcast-engine-wiring.py and a README 4.1 section. No em dashes, no triple-backtick fences, no Anthropic ids. Did NOT touch update.sh skill count / _index.json content_sha / version (merge phase owns those). |
| 2026-07-06 | W4.10/W4.11/W4.12 doc-updates-and-reuse-crossrefs | Opus 4.8 | DONE (branch, pre-merge) | feat/podcast-doc-updates-and-reuse-crossrefs | self 9.0 | Skill 23 how-to (engine + 4 presets + dashboard, doctrine kept authoritative); Skill 57 modes.md podcast boundary cross-ref; Skill 35 playbook s15 productionized-Podbean cross-link; Skill 30 fish ref updated to s2.1-pro (header selection, tag inventory, pricing, concurrency incl >=1000=50, s2.1-pro-free prohibition). Dept-Kit client how-to aligned operator-side (Downloads). No shared files touched; _index.json restamp deferred to merge. |
| 2026-07-06 | W4.10/W4.11/W4.12 doc-updates-and-reuse-crossrefs (verify+fix) | Opus 4.8 | DONE (branch, pre-merge) | feat/podcast-doc-updates-and-reuse-crossrefs | self 9.2 | Independently re-verified all four in-repo doc updates (Skill 23/30/35/57) against PRD Section 13 plus the operator-side Dept-Kit alignment (Downloads); confirmed 0 em dashes, 0 Anthropic ids, 0 client-facing GHL, no shared files touched. Fixed one cross-reference defect in Skill 23 how-to intro (presets pointed to Section 8; corrected to Section 9, engine to Section 8). |
| 2026-07-06 | W2.4 + W2.5 episode-qc-gates | Opus 4.8 exec | DONE (branch) | feat/podcast-episode-qc-gates | self-QC 9.2 | Added 58-podcast-production-engine/scripts/qc-tier1-mechanical.py (Gate B Tier 1 deterministic checks 1-11,15,16 at zero model cost; 12-14 DEFERRED to cheap judge tier) and qc-attempt-gate.py (attempt counter, targeted-retry + frozen-research enforcement, 3-strike stop with best draft). Both stdlib-only, fail-closed, config-overridable; self-tests 27/27 and 14/14 green; no em dash, no fence, no Anthropic deny-token in source. Episode gate only, never the 8.5 build gate. |
| 2026-07-06 | W1.11 Fish render module | Opus 4.8 (fish-render) | DONE (branch, merge-ready) | feat/podcast-fish-render | 9.0 self | 58-podcast-production-engine/scripts/generate_podcast_audio.sh adapted from Skill 35 per PRD Step 11. s2.1-pro header LIVE-VERIFIED (HTTP 200, audio/mpeg) and mp3_bitrate 192 verified. Client reference_id required; free tier s2.1-pro-free structurally refused; natural-beat split never mid-sentence or mid-tag with fail-closed bracket guard; condition_on_previous_chunks true; ffmpeg seamless join; two-pass loudnorm mastered and verified at -15.8 LUFS inside -16 to -14; ffprobe verify; shellcheck clean; 3-segment end-to-end render proven. Fish key SET or NOT SET only, never printed. |
| 2026-07-06 | W4.13 + W4.14 | Opus 4.8 (fleet-cf-revocation-and-routing) | DONE(branch-pushed; awaiting W6) | feat/podcast-fleet-cf-revocation-and-routing | self-QC 9.0 | Appended the fleet Cloudflare Access revocation runbook (three-blade kill switch application/edge/engine + podcast 9-step blades, revoke-podcast-client.sh, edge-only mode, churn cleanup) to docs/OPERATOR-MAINTENANCE.md; added the inbound-podcast-job dispatch rule (routing-only, department_slug podcast) to master-orchestrator-dept/SOP-00 (v1.5.0). Additive only; no em dashes added; no client names; no merge-owned files (update.sh, _index.json content_sha, version) touched. |
| 2026-07-06 | W1.22 Golden fixtures | Opus 4.8 exec | DONE | feat/podcast-golden-fixtures | Gate A self-scored 9.0 (build) | 46 files under 58-podcast-production-engine/examples/golden-modes/podcast/. Four presets: personal (solo, vulnerable, 1284 words, 550s), interview (counter_intuitive, guest they/them, 1179 words, 505s, plus 603-word teaser), season-strategy (8-episode slate, doc QC only), episode-asset-pack (idempotent regen). Both episodes pass all 16 Tier 1 checks and the 10-dim rubric floor of 8 (EPISODE gate). Shipped self-verifier verify-fixtures.py green. Zero em dashes, zero fences, zero Anthropic model refs; Fish s2.1-pro non-free; secrets referenced from env only. Additive only; did not touch update.sh, _index.json, or the version file. |
| 2026-07-06 | W1.24/W1.25 intake-questionnaires-and-payload | Opus 4.8 exec | DONE (branch) | feat/podcast-intake-questionnaires-and-payload | self-QC 9.3 | Added 58-podcast-production-engine/config/questionnaires/ (counter-intuitive, vulnerable, provocative, passionate, index) and config/payload-schema.json. Four NEW PODCAST question sets bound to the mapper per-style survey order (q-slots, roles, exact Convert and Flow field keys); canonical payload schema carries mode, style, preset, preferred_pronoun, podcast_id. Exact keys incl. double underscore in podcast_survey__additional_info. Hard-rule scans clean: 6/6 valid JSON, zero em/en dashes, zero code fences, zero deny-pattern tokens (claude/anthropic/opus/sonnet/haiku), slice files clean of client-name/operator-path tokens. Only slice files touched; update.sh, _index.json, version untouched (Merge owns those). |
| 2026-07-06 | W1.19+W1.20 | media-and-enrollment (Opus) | DONE(self-tests+52 pytest green) | feat/podcast-media-and-enrollment | 9.0 (self) | Tier3 media upload (folders lookup-only, HEAD-verify) + Skill44 caf enrollment (discovery/verify/enroll, double-enroll guard, hard Personal refusal, tag-based verify, STOP boundary). REST+caf only, no MCP, no Anthropic, no secrets printed. |
| 2026-07-06 | W1.6/W1.7/W1.23 modes-and-presets | Opus 4.8 exec | DONE (branch) | feat/podcast-modes-and-presets | self-QC 9.2 | Added 58-podcast-production-engine/modes/personal.md, modes/interview.md, config/presets.json. Perspective, cold-open/show-frame, transparency-beat handling per PRD Section 5 and CHECKLIST Part A; four output-type presets with mode-derived defaults, pipeline scope, terminal actions (interview enrolls, personal hard-refuses workflows and updates the spreadsheet). Hard-rule scans clean: valid JSON, zero em/en dashes, zero triple backticks, zero Anthropic tokens, no client-facing GHL name. Only slice files touched; shared files (update.sh, _index.json, version) untouched. |
| 2026-07-06 | W1.15 podbean-publish | Opus 4.8 exec | DONE (self-QC 9.2) | feat/podcast-podbean-publish | 9.2 | scripts/podbean_publish.sh: direct Podbean OAuth client_credentials + uploadAuthorize + PUT + episode create; own client_id/secret/podcast_id; ep number = count+1; title appends Inspired by speaker; publish or future+publish_timestamp on future release; ledger permalink idempotency skip; isolation guard on podcast_id; records via podcast_state.py; secrets never printed (curl config via process-substitution); shellcheck clean; 7 mock e2e tests + leak audit pass. |
| 2026-07-06 | W2.8 + W2.9 | runtime-guards (Opus 4.8) | DONE(self-test + py_compile + integration on branch) | feat/podcast-runtime-guards | 9.0 self | Authored scripts/guard-no-anthropic-runtime.py (file scan concrete Anthropic id shapes, dashboard stricter screen, routing tier assertion Ollama Cloud->OpenRouter->Gemini, deny_patterns armed, thinking-high only on Kimi/GLM, allowlist refuses runtime paths) and scripts/guard-cron-inventory.py (per-client exactly-one, no-heartbeat, no-poller, once-daily cadence bound, announce-mode check, churn sweep orphan proof; inventory + static + live modes). Both --self-test green; values never printed. Additive only; shared files untouched. |
