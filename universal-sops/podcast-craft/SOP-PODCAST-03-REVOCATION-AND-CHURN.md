# SOP-PODCAST-03: PODCAST REVOCATION AND CHURN (client leaves)

**Cluster:** Podcast-Craft Rules (`universal-sops/podcast-craft/`)
**Master authority:** `project-prds/podcast-engine/PRD.md` Section 13 (SOP plan) + `design/cloudflare-design.md` Section 3 (the 9-step revocation runbook and edge-only emergency mode) + `design/dashboard-design.md` (the three-blade kill switch) + `design/furnace-design.md` (the churn rule: a departed client leaves zero recurring jobs)
**Relationship to the fleet runbook (binding):** This SOP is an APPEND to the EXISTING fleet Cloudflare client-revocation runbook (the standard offboarding procedure the fleet already runs: revoke Access sessions, delete the Access app, cut DNS, remove tunnel ingress, rotate box secrets, remove the cron, verify from the edge). It is NEVER a competing document. The podcast-specific blades below extend that runbook; where the fleet runbook and this SOP overlap (Access, DNS, tunnel, cron), the fleet runbook is authoritative and this SOP adds only the podcast hostnames, the podcast hook mapping and secret, the dashboard token and service, the credit smoke-test cron, and the engine kill-blade.
**Owning role:** Operator.
**Enforcement pointer (binding):** `58-podcast-production-engine/scripts/revoke-podcast-client.sh` performs the runbook; every step is idempotent (safe to re-run), every step logs to the operator ledger, and the script never sends anything client-facing. Its own Step 9 verification is the enforcement: the revocation is not done until the script's independent end-to-end checks observe the edge dark, the hook dead, the box clean, and the gateway still healthy. The engine kill-blade is `58-podcast-production-engine/scripts/podcast_state.py deactivate-client`, after which the sole state writer refuses all further writes for that client (exit 4). Orphan-job hygiene is proven by `58-podcast-production-engine/scripts/guard-cron-inventory.py`, which asserts zero recurring jobs remain for a departed client.

---

## 0. WHY THIS SOP EXISTS

Revocation must be instant, unilateral, and complete: a departing client's access is cut from BlackCEO's own Cloudflare account with no dependency on the client, and the box is left clean with the gateway and every other service still healthy. A revocation that downs a box running other services, or that leaves a paid daily probe or a queued job behind, is a FAILED revocation. Order matters: kill live sessions before deleting routes, so no logged-in session outlives its hostname.

Preconditions: `CLOUDFLARE_API_TOKEN` confirmed SET (never printed); account id `13f808b72eb78027a8046357c6cf1afa`; zone `zerohumanworkforce.com` resolved by name or hardcoded (never the `CLOUDFLARE_ZONE_ID` environment variable). Every Cloudflare endpoint shape is LIVE-VERIFIED against current docs before scripting; paths and payloads drift.

## 1. THE THREE-BLADE KILL SWITCH

Three independent blades cut the client off, each usable alone; the full runbook drops all three plus box hygiene:

1. APPLICATION blade (dashboard): revoke live Access sessions, delete the Access app, cut the dashboard DNS, remove the dashboard tunnel ingress, invalidate `PODCAST_DASHBOARD_TOKEN`, stop the dashboard service. After this blade the dashboard cannot be reached or logged into.
2. EDGE blade (intake): remove or dead-route the podcast hook path at the tunnel, rotate/delete `PODCAST_INTAKE_HOOK_SECRET`, and (if BlackCEO manages the client's Convert and Flow workflows) disable the intake form's webhook action. After this blade no new intake can arrive.
3. ENGINE blade (state): `podcast_state.py deactivate-client <slug>` sets `podcast_client_state.active = 0`, after which the sole writer refuses every new state change for that client (exit 4). Even a resurrected route or an in-flight resume cannot advance a job. This blade is what makes the cutoff structural rather than merely edge-deep.

The application and edge blades are pure Cloudflare API plus box config; the engine blade is a single writer call on the box. Any one blade degrades the client; all three plus the box hygiene below is a complete offboard.

## 2. THE 9-STEP RUNBOOK (`revoke-podcast-client.sh <slug>`)

Step 1, revoke live dashboard sessions (instant lockout). Find the Access app for `<slug>-podcast.zerohumanworkforce.com` and revoke all active sessions/tokens for it (`POST /accounts/{account_id}/access/apps/{app_id}/revoke_tokens`). Anyone currently logged in is bounced immediately, before any DNS TTL games.

Step 2, delete the Access application (`DELETE /accounts/{account_id}/access/apps/{app_id}`). No new logins possible, allow-list gone. For a pause rather than an end, edit the policy to an empty allow-list instead of deleting; the default runbook deletes.

Step 3, cut the dashboard hostname at DNS. Look up and delete the DNS record for `<slug>-podcast.zerohumanworkforce.com`. The hostname stops resolving at the edge.

Step 4, remove tunnel ingress routes (dashboard plus the podcast hook path). Detect the tunnel config mode per box (remotely-managed config in Cloudflare via `cfd_tunnel/{id}/configurations` GET then PUT with the rule removed; or locally-managed `config.yml` edited over SSH then cloudflared restarted). If the hooks hostname is used ONLY by the podcast engine, remove it too; if it is shared with other skills, leave the hostname and remove only the podcast hook mapping in Step 5. Prove the tunnel back healthy (edge connections greater than zero) before calling the step done. Mac caveat: launchd LaunchAgents cannot be kickstarted over plain SSH (error 125); use the fleet-approved detached-restart pattern, never a blind `brew services restart` of a client Mac gateway path.

Step 5, disable and rotate the inbound webhook (on the box, as the correct runtime user, never root). Remove the podcast intake mapping from the OpenClaw hooks configuration; rotate/delete `PODCAST_INTAKE_HOOK_SECRET` in all env stores so even a resurrected route is dead; apply config per fleet gateway-restart doctrine (never `openclaw gateway restart` over SSH on a Mac; use the master-only kickstart or detached-run pattern; verify the gateway is back UP afterward). If BlackCEO manages the client's Convert and Flow workflows, disable the intake form's webhook action there too.

Step 6, invalidate the dashboard token and stop the dashboard service. Rotate/delete `PODCAST_DASHBOARD_TOKEN` from the box env stores; stop and deregister the dashboard service (PM2 delete on VPS boxes; launchd or cron watchdog removal on Mac boxes, same SSH discipline).

Step 7, stop the daily credit smoke test for this client. `openclaw cron list`, identify the podcast smoke-test job id, `openclaw cron rm <id>`; also remove any plain crontab fallback entry; verify with a fresh `openclaw cron list` and `crontab -l` that it is gone. This stops the daily paid API probes and the founder alerts for a client who no longer exists.

Step 8, drain the credit-out queue for this client. Any podcast jobs held in the credit-out queue are closed out as "client offboarded" (not "aged out"), and the founder is notified in the operator channel with the list of dropped job ids. Zero client-facing messages. Fire the ENGINE blade here: `podcast_state.py deactivate-client <slug>` so no held job can later resume and no new job can be created.

Step 9, independent end-to-end verification (no false done). `curl -sI https://<slug>-podcast.zerohumanworkforce.com` must NOT return the 302 to the Access team domain (expect a resolution failure or a Cloudflare 1016/530 class error); a dummy POST to the old hook URL must fail (route gone or hook 404, anything but a 2xx); Cloudflare API reads confirm no Access app, no DNS record, no ingress rule; box reads confirm no hook mapping, tokens absent from stores (SET-ness only), dashboard service not running, cron gone, and the gateway still healthy; `guard-cron-inventory.py` confirms zero recurring podcast jobs remain. Write the per-item ledger entry and post the operator report. Only then is the revocation done.

## 3. EDGE-ONLY EMERGENCY MODE (box unreachable)

Steps 1 to 4 are pure Cloudflare API and require no box access; they alone fully cut public access even if the box is dark. When a box is unreachable, run Steps 1 to 4 plus the edge checks of Step 9 (9a, the dashboard no longer returns the Access 302; 9b, the hook URL fails; 9c, the Cloudflare API confirms the Access app, DNS record, and ingress rule are gone), and record the box-side steps (5, 6, 7, and the on-box parts of 8) as PENDING for when the box returns. `revoke-podcast-client.sh` supports this mode explicitly.

## 4. CHURN RULE (zero recurring jobs left behind)

A departed client leaves zero recurring jobs on their box: no smoke-test cron, no queue poller, no per-job watcher, no heartbeat entry. `guard-cron-inventory.py` is the sweep that proves it; the revocation is not complete while any podcast recurring job survives for the slug. The engine blade (`deactivate-client`) plus Step 7 (cron removal) plus Step 8 (queue drain) together satisfy the rule. The credit-out queue is closed out with the departed-client reason, distinct from the 60-day age-out path.

## 5. SILENCE AND SECRECY

Zero messages to the client during any revocation step: no Telegram to the client's bot, no Convert and Flow message, no email. The revocation and provision scripts never source or trigger any client-notifying gate (for example, `qc-completeness.sh` is never run standalone during maintenance because it leaks a client Telegram alert). Operator-verbose: every revocation writes a ledger entry and posts a full step-by-step report to the operator, including the API call results and the Step 9 verification outputs. Secrets are confirmed SET or NOT SET only; no value is ever printed.
