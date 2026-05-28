<!--
Operator note: This file is a VERBATIM extraction from the source playbook
`openclaw-cloudflare-tunnel-prompt (1).md` (v5.14), lines 8086–8222 (Step 11 —
Pre-Handoff QC Checklist). No paragraphs were stripped, summarized, or reworded.
Do not edit content below this header without consulting the source playbook.
-->

## Step 11 — Pre-handoff QC protocol (full checklist)

Before declaring the run complete, the agent runs this exhaustive QC checklist. Every item must pass. If any fail, report the failure and either retry the relevant step or hand control back to the operator. This is the final gate.

### Phase-completion verification (cross-check checkpoints A through G)

- [ ] Checkpoint A — Orientation complete (Phase 0)
- [ ] Checkpoint B — Tunnel verified end-to-end (Phase 1)
- [ ] Checkpoint C — OpenClaw responds to inbound webhooks (Phase 2)
- [ ] Checkpoint D — Operator has copy-paste materials (Phase 3)
- [ ] Checkpoint E — Agent is safety-ready and memory-ready (Phase 4)
- [ ] Checkpoint F — Advanced features active (Phase 5)
- [ ] Checkpoint G — Capabilities documented (Phase 6)

### Infrastructure verification

- [ ] Cloudflare tunnel created and active (`TUNNEL_ID` captured, status confirmed via API)
- [ ] DNS CNAME exists and resolves to `<TUNNEL_ID>.cfargotunnel.com`
- [ ] `cloudflared` service is running AND auto-start flags verified
- [ ] Restart Survival Test passed (Step 2G — process killed, OS respawned with new PID)
- [ ] Public tunnel returns a response to `curl https://$PUBLIC_HOSTNAME/` (any 2xx/3xx/4xx)
- [ ] `openclaw.json` backup exists at `CONFIG_BACKUP_PATH`
- [ ] `hooks.mappings` entry for `HOOK_NAME` is present in `~/.openclaw/openclaw.json` with the correct `agentId` from Step 3B
- [ ] Multi-agent routing question (Step 3B) was asked and answered; `ROUTING_AGENT_ID` captured
- [ ] `openclaw config validate` exits clean
- [ ] Localhost smoke test (Step 3E) returned 200
- [ ] Public end-to-end test (Step 4) returned 200

### Credentials verification

- [ ] All five secrets (CLOUDFLARE_API_TOKEN, TUNNEL_TOKEN, HOOKS_TOKEN, TUNNEL_ID, CLOUDFLARE_ACCOUNT_ID) were appended to `SECRETS_ENV_FILE`
- [ ] API keys for chosen models present in env file

### Deliverables verification

- [ ] Client Reference Sheet created (Notion page URL captured OR markdown file path captured)
- [ ] Full playbook document was saved to `MASTER_FILES_DIR`
- [ ] Run Manifest exists at `RUN_MANIFEST_PATH` with all phases marked complete

### Agent behavior verification

- [ ] AGENTS.md backup exists
- [ ] AGENTS.md contains ALL inserted steps in correct order: Step 0.5 (quiet hours), Step 0.7 (compliance keywords), Step 1.2 (prompt injection protection — runs FIRST among 1.x steps), Step 1.3 (drift detection), Step 1.4 (safeguards), Step 1.5 (conversation log read), Step 1.6 (sentiment), Step 1.7 (typed knowledge bases), Step 1.8 (sales best practices), Step 1.9 (customer service & support), Step 1.75 (conversation workflow check + builder triggers), Step 2 (draft reply), Step 2.8 (humanizer pass), Step 2.5 (confidence threshold)
- [ ] All eight communication playbooks created with seed content
- [ ] AGENTS.md pointer section references real playbook URLs/paths (no `<will be added>` placeholders remain)

### Protocol documents verification

All of the following exist in `MASTER_FILES_DIR`:

- [ ] `conversation-log-protocol.md` (Step 9)
- [ ] `conversational-safeguards.md` (Step 9.5)
- [ ] `sentiment-monitoring-protocol.md` (Step 9.6)
- [ ] `pii-scrubbing-protocol.md` (Step 9.7)
- [ ] `quiet-hours.md` (Step 9.8)
- [ ] `compliance-keywords.md` (Step 9.9)
- [ ] `confidence-threshold-protocol.md` (Step 9.11)
- [ ] `conversation-export-protocol.md` (Step 9.12)
- [ ] `drift-detection-protocol.md` (Step 9.13)
- [ ] `knowledge-source-protocol.md` (Step 9.14)
- [ ] `prompt-injection-protection-protocol.md` (Step 9.15)
- [ ] `notification-routing-protocol.md` (Step 9.16, v5.3)
- [ ] `analytics-dashboard-protocol.md` (Step 9.17, v5.3)
- [ ] `document-generation-protocol.md` (Step 9.18, v5.3)
- [ ] `smart-booking-protocol.md` (Step 9.19, v5.3)
- [ ] `conversation-workflows/registry.md` (Step 9.20, v5.3)
- [ ] At least one Conversation Workflow file in `conversation-workflows/` (or operator deferred — noted in manifest)
- [ ] `humanizer-protocol.md` (Step 9.21, v5.5)
- [ ] Humanizer skill installed at `~/.openclaw/skills/humanizer*` (or install failure noted for later retry)
- [ ] `agent-capabilities-playbook.md` (Step 10)
- [ ] `conversational-logs/` folder
- [ ] `knowledge-sources/` folder with `registry.md`
- [ ] `document-templates/` folder (may be empty if operator deferred)
- [ ] `generated-documents/` folder (created lazily on first generation)
- [ ] `analytics/` folder (created lazily on first weekly digest)
- [ ] `conversation-workflows/` folder with `registry.md`

### Model and cron verification

- [ ] Model selection wizard (Step 3.5) completed: `REALTIME_MODEL_PRIMARY`, `ASYNC_MODEL_PRIMARY`, `BATCH_MODEL` all captured
- [ ] Chosen models exist in OpenClaw's `agents.defaults.models` catalog
- [ ] `model` field present in hooks.mappings entry; `fallbacks` chain configured
- [ ] Batch model present in cron job entry for `conversation-log-summarizer`
- [ ] Cron job `conversation-log-summarizer` registered and visible in `openclaw cron list`
- [ ] `system-health-heartbeat` cron registered (schedule: `0 9 1 * *`) and visible in `openclaw cron list`
- [ ] `analytics-weekly-digest` cron registered (schedule: `0 8 * * 1`, v5.3) and visible in `openclaw cron list`

### v5.3 Dreaming + Embeddings verification

- [ ] Self-Orientation O.6 ran — embeddings provider configured (Google text-embedding-004 default, or operator's existing provider preserved)
- [ ] `GEMINI_API_KEY` (or other provider key) present in env file
- [ ] Dreaming enabled in OpenClaw config with cron `0 3 * * *` and standard threshold gates (minScore 0.8, minRecallCount 3, minUniqueQueries 3)
- [ ] Dreaming cron job visible in `openclaw cron list`

### v5.3 Smart Booking verification

- [ ] Calendar system identified (Google / Convert and Flow native / Calendly / Outlook / other)
- [ ] If Google Calendar: OAuth token captured, calendar ID present, calendar accessible via `GET /calendar/v3/calendars/<id>`
- [ ] Booking rules captured: max window, min lead time, daily cap, excluded times, no-availability behavior, 3-strike escalation contact
- [ ] `BOOKING_CALENDAR_ID` and `BOOKING_RULES` captured in Run Manifest

### v5.4 Conversation Workflows verification (3-layer)

- [ ] `conversation-workflows/` folder + `registry.md` exist
- [ ] At least one workflow created during setup (or operator explicitly deferred all workflows — noted in manifest with reason)
- [ ] If workflows created with Layer 1 (new GHL routing required):
  - [ ] Required tags were created via GHL skill (NOT manually by operator); tag IDs captured in workflow's `--ghl-side.md` file
  - [ ] Workflow AI prompt saved as `<workflow-id>--workflow-ai-prompt.md` with all values (PUBLIC_HOSTNAME, HOOK_NAME, HOOKS_TOKEN, channel name, tag names) substituted in
  - [ ] Verification checklist saved as `<workflow-id>--verification-checklist.md` with brutally-specific items (each names the failure mode AND the fix)
- [ ] If workflows created without Layer 1 (existing routing covers them): Layer 0 decision documented in workflow file
- [ ] All workflows have: Trigger, Phases 1-4, Edge cases, On success, On escalation, Tone, Trigger keywords
- [ ] Registry lists all created workflows by id, name, trigger summary, Layer 1 status (yes/no), file paths for all layers

### Final completeness

- [ ] Teach Yourself Protocol completed — concise summary in active context, full doc on disk
- [ ] Run Manifest has zero `FAILED` checkpoint results
- [ ] Run Manifest deviations section reviewed — every deviation has a valid Rule 2(a) or 2(b) justification per Rules of Engagement

### Run Manifest seal

After all QC items pass, append the seal block to the Run Manifest:

```markdown
## Run Sealed

**Completed:** <ISO timestamp>
**Final status:** ALL CHECKS PASSED
**Total steps executed:** <count>
**Deviations logged:** <count>
**Artifacts created:** <list of file paths>
**Operator handoff:** delivered to <Notion URL or chat>
```

After QC passes AND the Run Manifest is sealed, present the final summary to the operator (Part 4 below).

---
