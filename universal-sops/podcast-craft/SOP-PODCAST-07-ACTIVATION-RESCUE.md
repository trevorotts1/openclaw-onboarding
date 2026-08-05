# SOP-PODCAST-07: ACTIVATION RESCUE (activating the processor on a box that is missing it)

**Cluster:** Podcast-Craft Rules (`universal-sops/podcast-craft/`)
**Skill:** 58-podcast-production-engine (the Podcast Production Engine)
**Owning role:** Operator (the fleet-wide rescue). The director-of-podcast observes the proof flow that closes the run.
**Stage:** On demand, once per box whose activation health fails, and fleet-wide whenever the activation audit names a box.
**Produces:** the four-layer activation (department agent, intake hook, scheduler, controller), one observed proof flow advancing `received -> researching` through the sole writer, the board card for that flow, and the operator ledger entry.
**Enforcement pointer (binding):** `58-podcast-production-engine/scripts/guard-activation-health.py` (the diagnosis primitive: checks the four layers against the wiring contract in `23-ai-workforce-blueprint/department-wiring/podcast-engine/wiring.json`, exit 0 when all four are present, nonzero with a JSON report naming every MISSING layer); `58-podcast-production-engine/scripts/install-podcast-department.sh` and `58-podcast-production-engine/scripts/register-podcast-hook.sh` (the activation scripts, both idempotent); `58-podcast-production-engine/scripts/podcast_step_driver.py` (the deterministic, no-daemon step driver: `podcast_step_driver.py next --job-id <id>` emits the EXACT next command for Steps 2-18 in the podcast agent's OWN turn); `58-podcast-production-engine/scripts/cc_board.py` (the fail-soft Command Center card caller); and `58-podcast-production-engine/scripts/podcast_state.py`, which remains the SOLE writer of engine state. A stage change recorded nowhere is not a stage change.

---

## 0. WHY THIS SOP EXISTS, AND THE ONE LAW

A box can be fully provisioned and still have NO processor. The edge, the tunnel, the DNS, the dashboard, the webhook route, and the secrets can all be green while the thing that actually runs an episode (the department agent, the bound intake session, the controller runbook that advances flows) was never installed on that box. The signature is exact: a real submission lands, the intake ledger records it in `received`, the client dashboard says Received, and nothing ever moves. The episode is not lost and not failed; it is stranded at the very first column. This SOP is the self-serve procedure that turns that box back on. It exists because a real ticket proved the gap: a client whose intake sat in `received` indefinitely because the processor had never been activated on her box. This document is that ticket generalized to the fleet.

The one law of SOP-PODCAST-01 binds unchanged here: every state change passes through `podcast_state.py`. Activation never hand-edits the intake ledger, never writes the SQLite database directly, and never moves a job by editing a file. The proof flow in Section 3 must advance through the sole writer or it does not count.

## 1. DIAGNOSIS (three independent confirmations, cheapest first)

The diagnosis is OBSERVED, never assumed. Run all three; they corroborate each other and they each fail on a different missing layer.

1. THE ACTIVATION HEALTH GUARD. Run:

       python3 58-podcast-production-engine/scripts/guard-activation-health.py --client <slug> --json

   The guard checks the four-layer processor stack (the dept agent, the intake hook route, the scheduler entry, the controller) against the wiring contract and reports each layer as PASS or MISSING. Exit 0 means the processor is present; a nonzero exit means at least one layer is missing and the JSON report names which. This is the same primitive the fleet-wide audit runs across every box on the roster, so the diagnosis here and the diagnosis in the audit are byte-identical.
2. THE DEPARTMENT AGENT. On the box, confirm `~/.openclaw/agents/dept-podcast/` exists AND `openclaw.json` carries exactly one `agents.list[]` entry with id `dept-podcast` whose `agentDir` resolves to that directory. A missing directory, a missing entry, or a duplicated entry each mean the processor is missing or corrupt. This is the exact runtime parity that `32-command-center-setup/scripts/materialize-dept-agents.sh` creates on a healthy box.
3. THE HOOK ROUTE AND THE CRON. Confirm the OpenClaw hooks configuration carries the route `podcast-intake-<slug>` with bound sessionKey `podcast:intake:<slug>` and a SecretRef of shape `{ source: env }` pointing at the intake secret label, and confirm `PODCAST_INTAKE_HOOK_SECRET` is SET in the LIVE gateway process environment (SET or NOT SET only, never the value). Separately, run `openclaw cron list` and `crontab -l`: a healthy box carries exactly ONE podcast recurring job, the daily credit smoke test `podcast-smoke-<slug>` (SOP-PODCAST-04 Section 1), no-deliver, no heartbeat, no second cron.

Corroborating evidence of the stalled state: the intake ledger at `~/.openclaw/state/podcast-engine/intake-ledger/<job_key>.json` holds a job in `received` with no forward transition recorded by the sole writer, and the client-clean dashboard shows the same job at Received. A job parked in `received` is the SYMPTOM; the three checks above name the CAUSE.

Diagnosis verdict: if all four layers are PASS and the flow still does not move, this is NOT an activation problem and this SOP stops. Route to SOP-PODCAST-04 (credit health; a FAIL service holds the job) or to SOP-PODCAST-01 Section 4 failure handling. Never run Section 2 on a box the guard already clears.

## 2. ACTIVATION (ordered, idempotent, as the runtime user)

Order matters: the department agent must exist before the hook binds a session to it, and the controller runs last so it wakes whatever the first three steps made runnable. Every script here is idempotent (safe to re-run); every step writes a ledger entry; all writes run as the runtime user (the node user), never root.

1. INSTALL THE DEPARTMENT. Run:

       install-podcast-department.sh

   It materializes the `dept-podcast` agent (directory, `openclaw.json` entry, persona binding per `wiring.json`) on this box. It WIRES the box into the existing universal podcast department; it never creates a second podcast department (per PRD Section 3.5 that is a build failure), it never touches sibling agents, and a re-run is a no-op when the agent already exists and healthy.
2. REGISTER THE HOOK. Confirm `PODCAST_INTAKE_HOOK_SECRET` is SET first (restore it from the client's env store per SOP-PODCAST-02 Section 2.2 if NOT SET; never invent a fresh value while another store still holds the real one, or live upstream deliveries will start failing auth). Then run:

       register-podcast-hook.sh --client-slug <slug>

   It registers (or re-registers) the route `podcast-intake-<slug>` bound to sessionKey `podcast:intake:<slug>`, owned by this client's podcast department agent only (`allowedAgentIds` is the podcast agent; `allowedSessionKeyPrefixes` is the podcast session namespace), with the SecretRef pointing at the intake secret label. Apply the config per the fleet gateway-restart doctrine (Mac: the master-only kickstart or the detached-run pattern, never a blind SSH restart of a client gateway path; VPS: compose recreate so env changes load), then confirm the gateway is back UP.
3. CONFIRM THE SCHEDULER. The processor's one recurring job is the daily credit smoke test created at provisioning. If the diagnosis found it missing, recreate it exactly per SOP-PODCAST-04 Section 1: one daily job at about 06:00 in the CLIENT'S timezone, named `podcast-smoke-<slug>`, with the no-deliver flag. Verify the delivery mode on the CREATED job, not just the flag (known CLI drift defaults a bare cron-add to announce mode and would spam the client chat). Then prove the inventory:

       python3 58-podcast-production-engine/scripts/guard-cron-inventory.py --client <slug>

4. WAKE THE STEP DRIVER. Run:

       python3 58-podcast-production-engine/scripts/podcast_step_driver.py next --job-id <id>

   The step driver is the runbook that advances flows in the podcast agent's OWN turn; `next --job-id <id>` emits the EXACT next command for Steps 2-18, and the agent runs it and records the stage change through `podcast_state.py advance`. One invocation is ONE deterministic pass, not a resident process: there is no daemon, no watcher, no resident poller, and activation adds no furnace to the box (SOP-PODCAST-04 Section 1 stands). This is the step that picks up any flow already parked in `received` while the processor was missing.

## 3. VERIFICATION (observed, never claimed; the run is not done until the flow moves)

1. THE PROOF FLOW ADVANCES. Preferred path: a real job was already parked in `received`. The `--once` pass in Section 2 Step 4 advances it, and `podcast_state.py get <job_key>` shows the transition `received -> researching` recorded by the sole writer (a legal forward adjacency per SOP-PODCAST-01 Section 2). Fallback path (no job parked): send ONE synthetic `_test: true` submission through the route, exactly the T4 payload from SOP-PODCAST-02 Section 3, signed with the route secret, honored only for the designated test contact. Observe its ledger record advance `received -> researching` and stop there per the `_test` contract (Step 0 and Step 1 dry checks only; no research, no draft, no publish, no enrollment, no client message). Delete the `test` ledger record afterward, same as onboarding does. A flow that does not move is NOT verified, no matter how green the layer checks are.
2. THE BOARD CARD APPEARS. The run lands on the Command Center podcast board through `cc_board.py` (workspace `podcast`, one card per job, idempotent create keyed by the job id) and the episode appears in the client-clean status on the dashboard. The board is fail-soft by contract: if `CC_BASE_URL` is unset the board is disabled and the run continues unboarded, which is recorded, not failed. Card absence with the board enabled is a verification failure; card absence with the board disabled is a note.
3. THE GUARD GOES GREEN. Re-run:

       python3 58-podcast-production-engine/scripts/guard-activation-health.py --client <slug> --json

   Exit 0, all four layers PASS. The fleet-wide audit re-run will now clear this box.
4. THE LOOP IS BOUNDED. The daily smoke test fires once and writes `state/health.json`; `guard-cron-inventory.py` still reports exactly one podcast cron. Activation must not leave a second recurring job behind.
5. THE RECORD. Write the per-step operator ledger entry and post the step-by-step report (layer verdicts before and after, the proof flow's job key and its observed transition, the board card id or the board-disabled note) to the operator channel. Zero client-facing messages: the client sees their job move on the dashboard, and nothing else.

## 4. ROLLBACK

Rollback removes exactly what this SOP added, in reverse order, and nothing else. It exists for a FAILED activation (a step that corrupts the gateway, a wrong box, a slug typo discovered after the fact), never as a substitute for revocation: SOP-PODCAST-03 owns a client leaving, including secret rotation, the engine kill-blade, and the churn sweep. Rollback never rotates secrets and never touches a live client's engine.

1. Remove the proof-flow artifacts: delete any `_test` ledger record Section 3 created. A real job that already advanced stays exactly where the sole writer put it; never move it backward by hand.
2. Remove the hook mapping: `register-podcast-hook.sh --remove <slug> podcast-intake-<slug>` (the identical call `revoke-podcast-client.sh` uses), apply the gateway-restart doctrine, and confirm the gateway is back UP. After this, unsigned and signed POSTs alike must fail (route gone); confirm with one dummy POST that returns non-2xx.
3. Remove any cron Section 2 Step 3 created: `openclaw cron rm podcast-smoke-<slug>` plus any crontab fallback entry; verify with `openclaw cron list` and `crontab -l`. Never remove a cron that predates this run on an onboarded client; confirm provenance in the ledger first.
4. De-materialize the department agent ONLY when this run created it on a box that should not carry it (wrong box, wrong slug). On any onboarded client's box, the podcast agent belongs there by design; leave it and escalate instead. The universal podcast department definition is never touched by any rollback: the floor stays 28.
5. Record the rollback in the operator ledger with the same step granularity as the activation, and re-run the diagnosis guard to confirm the box is back to its pre-rescue state.

## 5. THE FLEET-WIDE RULE (no client names, one procedure)

This SOP applies IDENTICALLY to every box on the fleet roster, and it contains no client name, hostname, or identifier: `<slug>` is a run-time placeholder resolved on the box, exactly as SOP-PODCAST-02 binds it. The fleet-wide posture, stated once:

- PROVISIONING PREVENTS. `provision-podcast-client.sh` delegates to the activation layer during onboarding (the hook-mapping delegate is one of its ordered steps). A box whose provisioning recorded a PENDING or FAIL delegation is a box with a known activation debt, and this runbook is how that debt is paid.
- REVOCATION REMOVES. `revoke-podcast-client.sh` removes the same layers (hook mapping first, then dashboard, cron, and queue drain) so a departed client never leaves processor residue behind. Revocation is SOP-PODCAST-03; this SOP never runs for a churned slug.
- THE AUDIT ENUMERATES. The fleet activation audit runs `guard-activation-health.py` across the roster and hands every MISSING verdict to this runbook, one box at a time, in silence. A fleet with a green audit has no box where an intake can park in `received` for want of a processor.

## 6. SILENCE, SECRECY, ISOLATION

Zero client-facing messages from any diagnosis, activation, verification, or rollback step; the operator channel is the only surface this SOP writes, and the founder path is alert dedup and nothing else. Secrets are referenced by LABEL and LOCATION only and reported SET or NOT SET plus a behavior probe; no value is ever printed, echoed, grepped, or pasted. The named client's own credentials only; nothing about one client's activation ever touches another client's box, slug, or secrets. Config writes run as the runtime user, never root. MOVE IN SILENCE: the visible product of this entire runbook is a job that quietly starts moving.

## 7. DEFINITION OF DONE FOR ONE ACTIVATION RESCUE

The rescue is done only when: the diagnosis guard exits 0 with all four layers PASS; the proof flow was OBSERVED advancing `received -> researching` through `podcast_state.py` (or the `_test` proof ran, was observed, and was cleaned up); the board card was observed, or the board-disabled state was recorded; `guard-cron-inventory.py` reports exactly one podcast cron; the operator ledger carries the full before-and-after record; and zero client-facing messages were sent. Anything less is not activated.
