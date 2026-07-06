# WAVE PLAN, PODCAST PRODUCTION ENGINE BUILD
### Execution directed acyclic graph: what runs in parallel, what MUST serialize
### Version 1.0, Fable, 2026-07-06

GLOBAL RULES (binding on every wave):
1. Model assignment: Opus 4.8 for every execution sub-agent; ONE Fable sub-agent for the dashboard build. Up to roughly 100 execution sub-agents total across all waves, but STAGGERED: never more than about 15 to 20 concurrent (roughly 40 or more concurrent trips the server rate limit); on a rate limit, stagger and resume with resumeFromRunId, never abandon.
2. Build in parallel on branches and pull requests ONLY. The onboarding repo has ONE merge-writer; ALL merges are serial in Wave 6. Command Center changes ride a separate serial train in the command center repo.
3. Every agent appends progress to TODO.md and SESSION-LOG.md (persist to disk so any session resumes cold). Every agent reports unprompted. A sub-agent's claim of done is a hypothesis until independently verified by the wave's verification step.
4. Gate A (8.5 build rubric) self-administered per unit before its pull request is marked merge-ready. Below 8.5: fix and re-run, autonomously.
5. Silence: zero client-facing messages from any wave. Never print secret values. Config writes as the node user. Client-facing name is Convert and Flow.
6. CANARY DOCTRINE: everything is proven on the operator box (/Users/blackceomacmini) first. NO client box is touched. Fleet rollout is HELD at repo-only until the operator gives the OK.

---

## WAVE 0: PREFLIGHT AND LIVE VERIFICATION (serialize entry, parallel inside; about 8 agents)

Nothing downstream starts until Wave 0's outputs are written to the build-state file.

- W0.1 Repo snapshot: confirm live onboarding repo baseline (v17.0.45 or current), branch strategy, G-gate inventory, update.sh current skill count, _index.json layout, department-floor.py podcast entry. Confirm master-files project-prds/ location for the PRD copy.
- W0.2 LIVE-VERIFY OpenClaw inbound webhook docs at openclaw.ai: Webhooks plugin route schema, SecretRef shapes, TaskFlow operations, against the INSTALLED gateway version on the operator box (schema drift is a known trap).
- W0.3 LIVE-VERIFY Fish Audio: s2.1-pro model header accepted by POST https://api.fish.audio/v1/tts (the endpoint enum lags the blog), voices and instant-voice-clone endpoints, mp3 at 192 output, condition_on_previous_chunks. Cheapest possible probes; never the free tier for anything client-related.
- W0.4 LIVE-VERIFY Cloudflare API shapes per cloudflare-design Section 6 (Access apps, revoke_tokens, tunnel configurations, DNS records, WAF rulesets, plan-tier allowances on the zone).
- W0.5 LIVE-VERIFY Podbean API (oauth client_credentials, uploadAuthorize, episodes) and the Skill 29 catalog for the media folder-create endpoint.
- W0.6 Reuse-asset inventory: pin exact paths and versions of Skill 57 podcast mode assets, Skill 35 generate_podcast_audio.sh and playbook section 15, Skill 30 reference, Skill 23 role library, Dept-Kit, NEW PODCAST questionnaires, podcast-agent identity.
- W0.7 Balance-endpoint discovery for config/smoke-endpoints.json (Ollama Cloud, OpenRouter GET /api/v1/key, Kie.ai credit lookup, Fish Audio wallet).
- W0.8 Copy the PRD folder into the onboarding branch at master-files project-prds/podcast-engine/ (PRD, session log, change log, to-do, checklist, QC protocol and matrix) so the repo carries the true PRD from the first commit.

DEPENDENCY: W0 outputs (a pinned facts file) feed every later wave. Anything LIVE-VERIFY that fails here is resolved here, not discovered mid-build.

## WAVE 1: CORE SKILL AUTHORING (fully parallel; about 28 agents, staggered in two batches)

Independent units, one agent each, all branch-and-pull-request:

- W1.1 Skill runbook (SKILL.md): the 18-step pipeline, presets, boundaries, silence rules.
- W1.2 to W1.5 Style Engine modules x4 (Counter Intuitive, Vulnerable, Provocative, Passionate): arcs, budgets, voice DNA, forbidden lists, worked-example calibration; seeded from Skill 57 prompt 17.
- W1.6 to W1.7 Mode modules x2 (Personal, Interview): perspective rules, cold-open and show-frame rules, transparency beat handling.
- W1.8 Research Assistant module: improvement, power statements, gap filling, case-study rules, 12-call cap wiring, package freeze.
- W1.9 Blueprint and sizing module: title rules, signature lines, budgets, 140 words per minute table.
- W1.10 Tagging module: S2.1 Pro square-bracket palette, density targets, mandatory locations, S1 conversion table.
- W1.11 Fish render module: adapt Skill 35 script; s2.1-pro header, reference_id, split-and-join, condition_on_previous_chunks, ffprobe verify, LUFS mastering, free-tier refusal.
- W1.12 Image module: Kie.ai GPT-image-2 per Skill 57 prompt 14; ffmpeg finalize chain; polling bounds.
- W1.13 Documents module: destination detection, Episode Package renderer, clean Speech Script, sharing rules.
- W1.14 Book teaser module: writing rules, fabrication boundary, book-typeset PDF renderer, 14-point floor.
- W1.15 Podbean publish module: per playbook section 15 plus the spec's step_b; idempotent permalink guard; scheduling.
- W1.16 Webhook layer: route template, deterministic mapper plus alias tables, job-key module, intake ledger, flow trigger, 409 helper, quarantine path.
- W1.17 Webhook fixtures and unit tests: Convert and Flow, Make.com, n8n sample payloads; collision and divergence tests.
- W1.18 Convert and Flow field layer: resolver (with CONVERTFLOW aliases INTO THE SHARED RESOLVER), field-map cache, batch-then-URL-last writer, read-back verifier.
- W1.19 Media upload layer: Tier 3 multipart, folder ensure logic, HEAD verification, filename rules.
- W1.20 Enrollment layer: Skill 44 discovery, verify-then-enroll, double-enrollment guard, Personal-mode hard refusal, spreadsheet updater.
- W1.21 Config set: consolidated furnace config, models routing with deny patterns, smoke-endpoints.json, cost-model.json, bands-style QC prover config.
- W1.22 Golden fixtures: one full golden episode per mode (adapting the Skill 57 golden-modes pattern), plus a Season-Strategy and an Asset Pack fixture.
- W1.23 Preset layer: the four output-type presets over the pipeline scope map.
- W1.24 Intake questionnaires wiring: NEW PODCAST question sets mapped to the mapper's per-style question order.
- W1.25 Canonical payload and input reference module.
- W1.26 Delivery report generator: report template, checklist reproduction, operator-channel-only sender.
- W1.27 Credit-out queue mechanics: hold, resume, 60-day age-out, payload purge.
- W1.28 Personal running spreadsheet: create-at-setup logic, append-per-episode, custom-field link storage.

## WAVE 2: GUARDRAIL AND ENFORCEMENT SUITE (fully parallel; about 12 agents; starts when W0 done, independent of W1)

- W2.1 podcast_state.py: sole writer, schema creation, transition matrix, all subcommands, redaction filter.
- W2.2 podcast-cost-ledger.py: precheck and record wrappers, ceilings, daily caps, token budgets.
- W2.3 podcast-smoke-test.py: balance-endpoint checks, self-metering, queue age-check and drain trigger.
- W2.4 qc-tier1-mechanical.py: all deterministic Tier 1 checks at zero model cost.
- W2.5 qc-attempt-gate.py: attempt counter, targeted-retry enforcement, frozen-research enforcement, 3-strike stop.
- W2.6 alert-dedup.py: keying, windows, storm cap, digest and recovery messages, gateway-only Telegram path.
- W2.7 ghl_credential_gate.py: full resolver sequence, pairing proof, fingerprint, field smoke test, rate floor, secrecy wrapper.
- W2.8 guard-no-anthropic-runtime.py: shipped-file scanner, routing-config assertions, allowlist policy.
- W2.9 guard-cron-inventory.py: one-cron assertion, no-heartbeat assertion, announce-mode check, churn sweep.
- W2.10 provision-podcast-client.sh: full provisioning per cloudflare-design Section 5 including the pass gate.
- W2.11 revoke-podcast-client.sh: the 9-step runbook, edge-only emergency mode, verification step.
- W2.12 T1 to T9 webhook verification script (executable, observed results, ledger-noted).

## WAVE 3: DASHBOARD (ONE Fable sub-agent; starts when W2.1 lands, because the schema writer is its dependency)

- W3.1 The Fable dashboard build: the /podcast route group inside the Command Center per design/dashboard-design.md in full, against podcast_state.py's schema, through all fourteen acceptance criteria. Rides the COMMAND CENTER repo's own serial train, coordinated with Wave 6 timing. Everything else in Wave 3 waits on nothing; W3 runs concurrently with W4.

## WAVE 4: WIRING, ROLES, SOPS, DOCS (parallel; about 14 agents; needs W1 skill shape settled)

- W4.1 Department wiring: attach the skill to the EXISTING podcast department; sessionKey binding; verify department-floor.py; NO new department.
- W4.2 Persona matching: bind director-of-podcast, podcast-host, audio-post-producer, qc-specialist-podcast, and the audio roles per PRD Section 13; QC independence rule wired.
- W4.3 Kanban wiring: ledger and database state enum to kanban columns; card lifecycle proof plan.
- W4.4 to W4.9 The six new SOPs (runbook, onboarding, revocation and churn, credit health, episode QC, book teaser), each with its enforcement pointer.
- W4.10 Doc updates batch 1: Skill 23 how-to-use-this-department, Dept-Kit client-facing how-to.
- W4.11 Doc updates batch 2: Skill 57 boundary cross-reference, Skill 35 playbook cross-link.
- W4.12 Doc update: Skill 30 Fish reference corrected to S2.1 Pro facts.
- W4.13 Fleet Cloudflare revocation runbook: append the podcast blades (never a competing runbook).
- W4.14 Master agent routing: inbound podcast job dispatch rule to the podcast department.

## WAVE 5: CANARY INTEGRATION ON THE OPERATOR BOX (mostly serial; about 8 agents; needs W1, W2, W4; W3 for its own checks)

- W5.1 Install the branch build on the operator box (canary; operator box is separate from the fleet).
- W5.2 Provision the operator box as a synthetic client (own secrets, own route, dashboard on 4010).
- W5.3 Execute T1 to T9 including T9 through the real public Cloudflare URL; record observed results.
- W5.4 Golden-fixture episode end to end with a _test-gated test contact: research through delivery, both documents, cover, audio, teaser, publish path exercised safely, link-back read-back, enrollment verify, dashboard reflects every stage, kanban card moves.
- W5.5 Force-failure drills: forced Tier 1 failure blocks delivery; forced rubric failure blocks; 3-strike stops and alerts (deduped); credit-out hold and resume; cost ceiling trips to cost_hold; duplicate webhook no-ops; wrong-tenant quarantines.
- W5.6 Gate battery: guard-no-anthropic-runtime, guard-cron-inventory, ghl_credential_gate full, silence and secrecy audit, fleet-wide client-name grep.
- W5.7 Gate A scoring of every unit; anything below 8.5 loops back to its owning agent, autonomously.
- W5.8 Revocation drill on the synthetic client, then re-provision (proves the churn path without touching any real client).

## WAVE 6: THE SERIAL MERGE TRAIN (ONE merge-writer agent; strictly serial; nothing else merges anywhere during it)

Order within the train:
1. Shared-resolver alias change (smallest blast radius) plus its content_sha restamp.
2. Skill directory (runbook, modules, configs, scripts, fixtures, tests).
3. Department, persona, kanban wiring.
4. SOPs and doc updates.
5. PRD folder sync at master-files project-prds/podcast-engine/.
6. update.sh skill-count correction.
7. hash-content-manifest.py restamp of _index.json content_sha across every touched file.
8. Version bump to v18.0.0.
9. ANNOTATED tag: git tag -a v18.0.0, created BEFORE the merge (G1 rejects bare tags).
10. Merge. Then fresh-clone verification: clone from GitHub, verify version, tag, skill count, content hashes, and that update.sh installs the skill cleanly.

The Fable dashboard merge rides the command center repo's own serial train at the same step-5 timing, cross-referenced in the change log.

## WAVE 7: POST-MERGE CANARY AND HOLD (serial; 2 agents)

- W7.1 Re-run W5.3 to W5.6 from the MERGED repo on the operator box (prove the merged artifact, not the branch).
- W7.2 Record the HOLD: fleet rollout is repo-only; no client box receives the skill until the operator OK. Final operator report: what merged, gate scores, canary evidence, the hold, and the per-client onboarding inputs awaiting founder confirmation (workflow triggers, Podbean podcast_id per client, snapshot fields, book_teaser field). Update memory and the session log. DONE only if CHECKLIST.md Part C is fully green.

---

## PARALLEL VERSUS SERIAL SUMMARY

PARALLELIZABLE (branch-only): all of Waves 1, 2, 4; Wave 3 alongside; Wave 0 items after W0.1.
MUST SERIALIZE: Wave 0 entry (repo snapshot first); W3.1 after W2.1; Wave 5 drills in order on the one canary box; the ENTIRE Wave 6 merge train; Wave 7.
HARD DEPENDENCIES: W0 facts file before any module pins an endpoint; W2.1 schema before W3.1 dashboard; W1 plus W2 plus W4 before W5; W5 fully green before W6; W6 before W7.

AGENT BUDGET: 8 + 28 + 12 + 1 (Fable) + 14 + 8 + 1 + 2 = 74 named agents, leaving about 25 of the 100 budget for re-dispatch, fix loops, and Gate A rework. Concurrency ceiling 15 to 20; stagger batches; resumeFromRunId on any rate limit; never stop the loop, re-dispatch on failure.
