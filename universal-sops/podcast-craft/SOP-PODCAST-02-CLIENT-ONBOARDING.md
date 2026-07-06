# SOP-PODCAST-02: PODCAST CLIENT ONBOARDING (per-client setup and go-live)

**Cluster:** Podcast-Craft Rules (`universal-sops/podcast-craft/`)
**Master authority:** `project-prds/podcast-engine/PRD.md` Sections 3, 5 (Step 0), 14, 15 + `design/webhook-design.md` Section 8 + `design/cloudflare-design.md` Section 5 + `design/ghl-design.md` Sections 2, 3, 5
**Owning role:** Operator. Every step here is operator-driven and runs on the client's OWN box against the client's OWN credentials. The client is never messaged by this SOP; the one welcome message carrying the dashboard link is sent by the standard Convert and Flow onboarding workflow, not by the engine.
**Enforcement pointer (binding):** `58-podcast-production-engine/scripts/provision-podcast-client.sh` and its pass gate (Cloudflare 302-to-Access check, a signed test POST accepted on the hook, the smoke-test cron fired once); `58-podcast-production-engine/scripts/verify-t1-t9.sh`, the T1 to T9 onboarding verification executable, which must be EXECUTED and OBSERVED (through the real public URL for T9), never asserted; and `58-podcast-production-engine/scripts/ghl_credential_gate.py` in full mode, whose exit codes (0 pass, 2 credential missing, 3 isolation violation, 4 required custom fields missing, 5 rate floor not met) gate whether the client may go live. The state schema is created by `58-podcast-production-engine/scripts/podcast_state.py init`. No pass, no go-live.
**Stage:** Runs once per client, after the AI Workforce Interview gate and as part of podcast engine enablement.

---

## 0. WHY THIS SOP EXISTS, AND THE GATES

Onboarding is where isolation, funding, and reachability are proven BEFORE any episode depends on them. A false "onboarded" produces a client whose first real submission dies mid-publish or, worse, writes into the wrong tenant. Every checkpoint below has a script and an exit code, so onboarding is observed, not claimed. Independent verification rule: onboarding is not done until the T1 to T9 table has actually been executed and observed, end to end, on that client's box, with results noted in the setup record.

All credentials are documented by LABEL and LOCATION only; verification is always SET or NOT SET plus a behavior probe. No value is ever printed, echoed, grepped into a report, or pasted into chat. All credentials are the NAMED CLIENT'S OWN accounts; no operator, shared, agency, or other-client credential ever substitutes. Config writes run as the correct runtime user (the node user on Docker boxes), never root, because a root-owned config freezes the gateway.

## 1. PRECONDITIONS

1. The AI Workforce Interview gate is complete for this client (Command Center provisioning is downstream of that interview by design).
2. The podcast department already exists on the universal floor (id `podcast`); onboarding WIRES this client's box into it and never creates a duplicate.
3. A per-client slug is chosen (lowercase, dash-separated, stable for the life of the client), used everywhere below as `<slug>`. The repo is fleet-wide: no real client name, hostname, or identifier is ever written into any repo file; `<slug>` is a provision-time placeholder resolved on the box.

## 2. THE ONBOARDING SEQUENCE

### 2.1 Credential gate, full mode (before anything else touches Convert and Flow)

Run `ghl_credential_gate.py --client <slug> --expected-location-id <id> --state-dir <dir> --mode full --check-fields --json`. It resolves the Location Private Integration Token (prefix `pit-`) through the full alias set and the ENV-CHECK-BEFORE-FAIL sequence (live gateway process environment first, then every env-store file, then `openclaw.json` both `env.vars.<KEY>` and root `env.<KEY>`, then `auth-profiles.json`, then a filename-only `grep -ril 'pit-'` sweep), proves the token pairs against the Location with a live `GET /locations/{id}`, computes and checks the anti-commingling fingerprint, runs the custom-field smoke test (every REQUIRED key present, exact match, including the double underscore in `podcast_survey__additional_info`), and checks the rate floor. Exit handling: 0 proceed; 2 the credential is genuinely missing everywhere (fix the env store, never guess); 3 isolation violation (pairing mismatch or commingling: HARD ABORT plus founder alert, never proceed); 4 required custom fields missing (route the client to support to install the snapshot; never create the standardized fields silently); 5 rate floor not met (queue and retry). Confirm the client's OWN Fish Audio key and `reference_id`, Kie.ai key, Podbean credentials, and Ollama Cloud or OpenRouter key are SET in the same run's scope (labels and locations recorded, values never printed).

### 2.2 Webhook route and secret

Generate the route secret with `openssl rand -hex 32`; write it to the client's env store as `PODCAST_INTAKE_HOOK_SECRET` (verify SET in the LIVE process environment, not just in a file), or to `~/.openclaw/secrets/podcast-intake.secret` mode 0600 owned by the runtime user. Add the OpenClaw Webhooks plugin route: id `podcast-intake-<slug>`, bound sessionKey `podcast:intake:<slug>` (owned by this client's podcast department agent), SecretRef `source: env` pointing at `PODCAST_INTAKE_HOOK_SECRET`. Validate the route against the INSTALLED gateway's schema before applying (schema drift is a known trap; the installed contract keys the routes map at `plugins.entries.webhooks.config.routes` and the SecretRef is exactly `{ source, provider, id }`). Apply per the box's restart doctrine (Mac: the kickstart-then-stop sequence; VPS: compose recreate so env changes load), then confirm the gateway is healthy. The plaintext secret transits no chat, no document, no repo, no log.

### 2.3 Cloudflare provisioning

Run `provision-podcast-client.sh <slug> <client-email(s)> <timezone>`. It discovers the client's ONE existing named tunnel and its config mode via the Cloudflare API (never guesses), adds ingress for the dashboard (loopback `127.0.0.1:4010`) and for hooks (loopback `127.0.0.1:18789`, reusing an existing hooks hostname when one is already routed), creates the DNS CNAME(s) to `<tunnel-id>.cfargotunnel.com` proxied in zone `zerohumanworkforce.com` (zone id resolved by name or hardcoded; NEVER trust the `CLOUDFLARE_ZONE_ID` environment variable, which points at the wrong zone), and creates the Access app "Podcast Dashboard - <slug>" whose allow-list is exactly the client's own email(s) plus `trevelynotts@gmail.com` plus `trevor@blackceo.com`. It generates `PODCAST_INTAKE_HOOK_SECRET` and `PODCAST_DASHBOARD_TOKEN` into the env stores (confirm SET), deploys the read-only dashboard service on `127.0.0.1:4010`, and creates the daily credit smoke-test cron at about 06:00 in the CLIENT'S timezone with the no-deliver flag (the default announce mode spams the client chat; verify the delivery mode on the CREATED job, not just the flag). Gate: `curl -I https://<slug>-podcast.zerohumanworkforce.com` must return HTTP 302 to the Access team domain; a signed test POST is accepted on the hook; the smoke-test cron fires once. No pass, no done.

### 2.4 Skill 44 workflow discovery (never guessed, never auto-built)

Via Skill 44 `caf` workflow listing, resolve both workflow names to IDs and record each workflow's ACTUAL trigger mechanism (direct add, tag-triggered plus which tag, or field-triggered plus which field) into the per-client state file: `06-Podcast_Episode_Is_Ready` and `04-Podcast is Completed` (documented as field-change triggered by the Podcast Survey Episode URL; verify per account). If either workflow is missing by name, STOP setup for this client and surface it to the founder; building a workflow is a Skill 44 build operation requiring the separate Firebase refresh token and an operator decision, never an autonomous runtime act.

### 2.5 Podbean podcast_id capture

Capture the client's Podbean `podcast_id` at onboarding into the per-client state and env store. The canonical payload REQUIRES it and the mapper refuses to guess it; publishing to the client's own channel (Step 15) cannot proceed without it. Confirm the OAuth client_id and client_secret resolve and that a client_credentials token can be minted (a dirt-cheap probe, not a publish).

### 2.6 Running spreadsheet creation (Personal mode)

For a client on the Personal Podcast preset, create the running episode spreadsheet at setup (create-at-setup logic, not per episode). Step 17 for Personal mode appends one row per episode and touches no workflows and sends no messages. Record the spreadsheet location in the per-client state; Interview-only clients skip this.

### 2.7 book_teaser field reminder

The `book_teaser` custom field (Interview mode) may not exist in the client's account. The credential gate reports it as `present` or `ABSENT`. If absent, surface a founder reminder to create a custom field named `book_teaser`, note the absence in the delivery report, and NEVER silently create it and NEVER fail an episode over it. This is a founder reminder, not a build blocker.

### 2.8 Upstream sender and sample payload

Configure the ONE upstream sender the client actually uses (a Convert and Flow workflow webhook action, Make.com, or n8n): method POST, the public URL, header `Authorization: Bearer <secret>` (value pasted from the credential store, never from chat), a FLAT JSON body carrying the survey fields plus `contact_id`, `location_id`, `podcast_id`, mode, and style. Capture one real sample payload and add it to the mapper's test fixtures so the deterministic mapper stays covered for this pipeline family. Record route id, sessionKey, secret LOCATION (env var name or file path, never the value), upstream pipeline type, sample payload fixture path, and date in the setup notes.

## 3. TEST-SUBMISSION VERIFICATION (T1 to T9; all must pass before go-live)

Execute `verify-t1-t9.sh` and observe every result. T1 through T8 exercise the loopback path; T9 re-runs the T4 case through the real public Cloudflare URL to prove the tunnel and edge, not just local wiring.

| # | Test | Expected |
|---|---|---|
| T1 | POST with no auth header | 401, nothing written |
| T2 | POST with wrong secret | 401, nothing written |
| T3 | POST with the secret in the query string only | rejected (the platform refuses query tokens), nothing written |
| T4 | POST a full synthetic payload with `_test: true` and the correct secret | 200 accepted; ledger record in state `test`; every canonical field extracted; the flow runs Step 0 and Step 1 dry checks only and stops; no research, no draft, no publish, no enrollment, no client message |
| T5 | Re-POST the identical T4 payload | 200 duplicate; delivery_count 2; no second record, no second flow |
| T6 | POST the T4 payload with one answer changed | 200 accepted; NEW job key and NEW record in state `test` (proves hash sensitivity) |
| T7 | POST a payload whose `location_id` is a different tenant | accepted-incomplete or quarantine; operator alert fired; nothing processed |
| T8 | POST a payload missing `style` | ACK; state `needs_input`; operator alert names the missing field |
| T9 | Run the T4 case through the real public URL | same result as T4 (proves tunnel plus edge) |

The `_test: true` flag is honored ONLY for payloads whose contact identifiers match the designated test contact recorded at onboarding; test records never touch Podbean, never write custom fields, never enroll workflows. Delete the `test` ledger records after verification.

## 4. SILENCE, SECRECY, ISOLATION

Zero client-facing messages from any onboarding step. Never print a secret value; report SET or NOT SET only. Never commingle clients; the named client's own keys only. Config writes as the runtime user, never root. Operator-verbose: every provision writes a ledger entry and posts a full step-by-step report to the operator, including API call results and the independent verification outputs.

## 5. DEFINITION OF DONE FOR ONBOARDING

Onboarding is done only when: the credential gate passed full mode (exit 0) with the field smoke test and pairing proof; the webhook route and secret are in place and a signed test returns 200 while unsigned returns 401; the provision gate passed (302 to Access, signed hook POST accepted, smoke-test cron fired once with no-deliver confirmed on the created job); both workflows are discovered by name with their real triggers recorded (or setup was stopped and surfaced); the Podbean `podcast_id` is captured; the running spreadsheet exists for Personal mode; the `book_teaser` reminder is resolved or noted; and T1 through T9 were executed and observed, including T9 through the real public URL. The setup record carries every LOCATION and every observed result. Anything less is not onboarded.
