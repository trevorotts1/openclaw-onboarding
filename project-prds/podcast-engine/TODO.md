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
- [ ] W1.22 Golden fixtures (both modes plus Season-Strategy plus Asset Pack). PENDING
- [ ] W1.23 Preset layer (4 output types over the pipeline scope map). PENDING
- [ ] W1.24 Intake questionnaire wiring (NEW PODCAST question order tables). PENDING
- [ ] W1.25 Canonical payload module. PENDING
- [ ] W1.26 Delivery report generator (operator channel only). PENDING
- [ ] W1.27 Credit-out queue mechanics (hold, resume, 60-day age-out). PENDING
- [ ] W1.28 Personal running spreadsheet logic. PENDING

## WAVE 2: GUARDRAIL SUITE (12 Opus 4.8 agents, parallel)
- [ ] W2.1 podcast_state.py (sole writer, transition matrix, redaction). PENDING
- [ ] W2.2 podcast-cost-ledger.py (ceilings, caps, budgets). PENDING
- [ ] W2.3 podcast-smoke-test.py (at or under 1 cent; queue age check). PENDING
- [ ] W2.4 qc-tier1-mechanical.py (deterministic Tier 1). PENDING
- [ ] W2.5 qc-attempt-gate.py (3-strike, targeted retries, frozen research). PENDING
- [ ] W2.6 alert-dedup.py (windows, storm cap, gateway-only path). PENDING
- [ ] W2.7 ghl_credential_gate.py (resolver, pairing, fingerprint, fields, rate floor). PENDING
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
- [ ] W4.13 Fleet Cloudflare revocation runbook: podcast blades appended. PENDING
- [ ] W4.14 Master agent routing rule for inbound podcast jobs. PENDING

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
