# SOPs Mirror -- Capacity and Reliability Engineer

**Source:** presentations/capacity-reliability-engineer.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- System Capacity Probe and Fleet Sizing

**When to run:** Step 0.5 -- immediately after media library creation (Step 0 / SOP 9.1 of media-librarian-ghl-updater) and before Phase A (discovery interview) begins. The Director must wait for capacity_plan.json before dispatching any sub-agents.

**Inputs:**
- Client's box credentials (SSH / cwd access)
- Client's env stores (OLLAMA_API_KEY, OPENROUTER_API_KEY, KIE_API_KEY)
- working/copy/mission_prd.json (slide_count_final -- for budget calculation)

**Steps:**
1. Run the probe commands on the client's box. Record all outputs:
   ```bash
   free -h            # Total RAM, used RAM, free RAM
   nproc              # CPU core count
   uptime             # 1/5/15-minute load averages
   df -h              # Disk space (focus on home partition)
   ```
2. Parse the outputs. Extract:
   - `free_ram_gb`: free RAM at probe time (use the "free" column from `free -h`, NOT the advertised total -- on oversubscribed VPS, use free RAM as the actual budget)
   - `cpu_cores`: from nproc
   - `cpu_load_15min`: the 15-minute load average from uptime (stable load indicator)
   - `free_disk_gb`: available disk on the home partition
3. Test Ollama Cloud reachability: send one live test turn to the client's OLLAMA_API_KEY against the `kimi-k2.6:cloud` model. Record: `ollama_cloud_reachable: true/false`. If the model is NOT reachable with the cloud URL (requires `models.providers.ollama.baseUrl = https://ollama.com`): flag to the Director and propose using OpenRouter fallback for text models.
4. Check Kie.ai credit balance: call the Kie.ai balance endpoint with the client's KIE_API_KEY. Record: `kie_credits_remaining`.
5. Calculate image generation budget: SLIDE_COUNT x 2 x $0.03. Record as `budget_ceiling`.
6. Compare `kie_credits_remaining` to `budget_ceiling`. If credits < budget_ceiling: flag to the Director BEFORE the run begins: "Insufficient Kie.ai credits for this run (need $X, have $Y). Operator must top up before Phase 4."
7. Apply the fleet sizing table:
   | Free RAM at probe | Max concurrent sub-agents (total) | QC agents | Writer agents |
   |---|---|---|---|
   | under 4 GB | 4 | 3 | 1 |
   | 4-8 GB | 6 | 4 | 2 |
   | 8-16 GB | 8 | 6 | 2 |
   | over 16 GB | 10-12 | 8-10 | 2-4 |
   If CPU load_15min > 0.8 x cpu_cores: reduce the recommended agents by 2 (box is already busy).
   If any model runs LOCALLY (not cloud): reduce to max 2 concurrent agents (local model = I/O bound, not scale-out).
8. Write capacity_plan.json:
   ```json
   {
     "client_slug": "...",
     "deck_slug": "...",
     "probe_at": "ISO timestamp",
     "free_ram_gb": N,
     "cpu_cores": N,
     "cpu_load_15min": N,
     "free_disk_gb": N,
     "ollama_cloud_reachable": true,
     "kie_credits_remaining": N,
     "budget_ceiling": N,
     "budget_ok": true,
     "model_location": "cloud|local",
     "max_concurrent_agents": N,
     "qc_agents_recommended": N,
     "writer_agents_recommended": N,
     "go_nogo": "GO|NOGO",
     "nogo_reason": null
   }
   ```
9. Write go_nogo:
   - GO: free_ram_gb >= 2, free_disk_gb >= 10, budget_ok = true, ollama_cloud_reachable OR openrouter_available.
   - NOGO: any of the above conditions fails.
10. If NOGO: notify the Director and the operator immediately. Do not proceed.
11. Verify python-pptx, LibreOffice, and poppler-utils (pdftoppm) are installed on the client's box. These are required by the PPTX Assembly Specialist. If any are missing, flag to the Director: "[TOOL] is not installed. PPTX assembly will fail at Phase 6 unless this is resolved."

**Outputs:**
- working/checkpoints/capacity_plan.json (complete)

**Hand to:** Director (who reads the fleet sizing recommendations before dispatching Phase 1 agents)

**Failure mode:** If the probe commands fail (e.g., SSH access error, box is offline): report the error to the Director. The run cannot proceed until the box is reachable.

---

### SOP 9.2 -- Resilience Watchdog Cron and Checkpoint Recovery

**When to run:** Phase 7 -- after the Slide Submitter begins Phase 4 (image generation). The watchdog runs every 10 minutes for up to 90 minutes or until the run reaches DONE status, whichever comes first.

**Inputs:**
- working/checkpoints/ (directory of all checkpoint JSON files)
- capacity_plan.json (for client_slug and deck_slug)

**Steps:**
1. Verify the installer-scheduled watchdog is live: Mac `launchctl list | grep com.blackceo.presentation-watchdog`; VPS `openclaw cron list | grep presentation-watchdog`. If absent, run `update-skills.sh` (it re-asserts the schedule). Never write or install a per-deck watchdog.
2. Record `watchdog: installer-managed` in `capacity_plan.json`.

**Outputs:**
- working/scripts/watchdog.sh (installed and running every 10 minutes)
- working/checkpoints/watchdog.log (updated every 10 minutes)
- capacity_plan.json (watchdog_installed, watchdog_removed, stall_threshold_minutes, watchdog_max_runtime_minutes)

**Hand to:** Director (receives first-stall alert for self-heal attempts); Operator (receives second-stall alert or failed self-heal notification); ROLE-16 Healer -- Presentations (on second consecutive stall or failed self-heal: hand off with the full incident package -- stall count, checkpoint state, self-heal attempt log -- so the Healer can root-cause and permanently patch the SOP that allowed the stall)

**Failure mode:** Verify the installer-scheduled watchdog is live: Mac `launchctl list | grep com.blackceo.presentation-watchdog`; VPS `openclaw cron list | grep presentation-watchdog`. If absent, run `update-skills.sh` (it re-asserts the schedule). Never write or install a per-deck watchdog.

---

### SOP 9.3 -- Model Routing and Env-Store Verification

**When to run:** During Step 0.5 probe, before capacity_plan.json is written. Verifies that all required API keys are present and functional before the run begins.

**Inputs:**
- All client env stores: `~/.openclaw/workspace/.env`, `~/clawd/secrets/.env`, openclaw.json env.vars, and the running gateway process env.

**Steps:**
1. Check ALL four env stores for the following keys. Do NOT declare a key missing after checking only one store:
   - KIE_API_KEY
   - OLLAMA_API_KEY
   - OPENROUTER_API_KEY
   - GHL location ID and API token (field names vary -- check intake.json for the specific field names this client uses)
2. For each key found: record its location in capacity_plan.json under `env_store_locations`: `{ "key": "KIE_API_KEY", "found_in": "~/.openclaw/workspace/.env" }`.
3. For each key NOT found in any store: record `{ "key": "KIE_API_KEY", "found_in": "NOT FOUND" }`. Notify the Director: "Key [KIE_API_KEY] not found in any env store. Phase 4 will fail without it."
4. Verify model routing. For text models (Phase 1, Phase 3 QC agents, Phase 5 QC agents):
   a. Attempt one live test turn to `ollama/kimi-k2.6:cloud` with the client's OLLAMA_API_KEY.
   b. If successful: `primary_text_model: "ollama/kimi-k2.6:cloud"`.
   c. If unsuccessful: attempt one live test turn to the same model via OpenRouter with the client's OPENROUTER_API_KEY.
   d. If OpenRouter successful: `primary_text_model: "openrouter/moonshot/kimi-k2"` (or equivalent slug).
   e. If both fail: `primary_text_model: "UNAVAILABLE"`. NOGO decision. Notify Director.
5. Verify QC model (qwen3-vl:235b-cloud via Ollama Cloud or OpenRouter — independent from the producer; no self-grading). Same process as step 4.
6. Write model routing table to capacity_plan.json:
   ```json
   {
     "model_routing": {
       "text_primary": "...",
       "text_fallback": "...",
       "qc_primary": "...",
       "qc_fallback": "...",
       "image_model": "per-MODEL-MANIFEST"
     }
   }
   ```

**Outputs:**
- capacity_plan.json (env_store_locations and model_routing sections complete)

**Hand to:** Director (informs all specialists which model routing to use for this run)

**Failure mode:** If a live test turn fails due to a network timeout (not an auth error): retry once after 30 seconds. A single timeout is not sufficient to declare a model unavailable. Two consecutive failures = flag to Director.

---
