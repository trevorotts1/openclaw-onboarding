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
- [ ] W3.1 Fable dashboard build per design/dashboard-design.md, all fourteen acceptance criteria; command center repo serial train. PENDING

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
| 2026-07-06 | W2.4 + W2.5 episode-qc-gates | Opus 4.8 exec | DONE (branch) | feat/podcast-episode-qc-gates | self-QC 9.2 | Added 58-podcast-production-engine/scripts/qc-tier1-mechanical.py (Gate B Tier 1 deterministic checks 1-11,15,16 at zero model cost; 12-14 DEFERRED to cheap judge tier) and qc-attempt-gate.py (attempt counter, targeted-retry + frozen-research enforcement, 3-strike stop with best draft). Both stdlib-only, fail-closed, config-overridable; self-tests 27/27 and 14/14 green; no em dash, no fence, no Anthropic deny-token in source. Episode gate only, never the 8.5 build gate. |
