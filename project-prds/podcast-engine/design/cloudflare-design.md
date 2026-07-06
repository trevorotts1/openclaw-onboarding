# Podcast Production Engine - Cloudflare Strategy Design
## Per-client inbound webhook public URL + client-facing dashboard hosting
### Version 1.0 - Fable design spec - 2026-07-06

Status: DESIGN APPROVED FOR BUILD (score target >= 8.5). Items marked LIVE-VERIFY must be
confirmed by the /goal build agent against current Cloudflare and OpenClaw documentation
before wiring; endpoint shapes drift and this doc must not be treated as a substitute for
the live docs.

Sources: CLAUDE_CODE_BUILD_BRIEF.md (web_research_required), PODCAST_EPISODE_GENERATION_SYSTEM.md
(ingress_and_trigger_boundary, required_credentials_and_health, client_dashboard), operator
fleet doctrine (memory: client-public-cc-zhw-link-location, client-command-center-links,
cloudflare-zone-ids, mac-client-gateway-launchd-ssh, openclaw-ghl-hook-mechanics).

---

## 0. Hard constraints (non-negotiable, inherited from operator doctrine)

1. Cloudflare Tunnel ONLY. Tailscale is banned. Never suggest it, never fall back to it.
2. The client's public link is managed via the Cloudflare application programming interface
   (the API). The public link lives in Cloudflare (Domain Name System record + Access app +
   tunnel ingress), NOT in openclaw.json. Never conclude "no link" from openclaw.json.
3. The OpenClaw gateway binds loopback only: 127.0.0.1:18789. It is never exposed directly.
   All public HTTPS terminates at Cloudflare and reaches the box through a named Cloudflare
   Tunnel (cloudflared) running on that client's box.
4. Per-client isolation. One tunnel per client, one Access app per hostname per client, one
   webhook secret per client. No wildcard Access apps spanning clients. No shared secrets.
   Never commingle clients.
5. Repo is fleet-wide. No client names, hostnames, or identifiers in the onboarding repo.
   Everything below is parameterized by a per-box client slug resolved at provision time.
6. Secrets discipline: scripts confirm a secret is SET (non-empty), never print its value.
7. Silence: no client-facing operational messages, ever. Operator-verbose only. Convert and
   Flow (GoHighLevel) owns ALL customer messaging (responsibility boundary in the spec).

---

## 1. DECISION: BlackCEO-hosted Cloudflare (RECOMMENDED) vs client-hosted Cloudflare

### Recommendation: BlackCEO-hosted Cloudflare. Firm.

The dashboard and the inbound webhook both ride BlackCEO's existing Cloudflare account
(account ID 13f808b72eb78027a8046357c6cf1afa) on the zerohumanworkforce.com zone
(zone ID a9ecc0a067f52eaa4c59dc9b11d9dd55). This is not a new pattern; it is the pattern
the entire fleet already runs. Ten clients already have Command Centers at
`<slug>.zerohumanworkforce.com` behind BlackCEO Cloudflare Access on team domain
sweet-wave-ca28.cloudflareaccess.com, each fronting a dedicated per-client tunnel.
The podcast engine simply adds hostnames to the machinery that already exists.

### Why BlackCEO-hosted wins

1. Central control and trivial revocation. One API token, one account, one zone, one Access
   team. Cutting a departing client off is four to six API calls that BlackCEO alone can
   execute, and the client cannot undo them. On client-hosted Cloudflare, revocation would
   depend on credentials in an account the CLIENT owns; the client could re-grant themselves
   access, and BlackCEO could be locked out at any time.
2. Credential doctrine. Operating inside a client's Cloudflare account requires holding that
   client's Cloudflare API tokens. Fleet doctrine forbids touching client credentials for
   BlackCEO-operated infrastructure. BlackCEO-hosted requires zero client credentials.
3. Uniformity. One provisioning script, one revocation script, one verification probe works
   for every client. Client-hosted means N accounts, N plans with different feature sets
   (Access seats, rate limiting availability), N failure modes.
4. The spec itself leans this way: "A central benefit of BlackCEO hosting is access control:
   if a client stops working with BlackCEO, their access to the dashboard and the podcast
   engine can be cut off."

### Tradeoffs, stated honestly

| Dimension | BlackCEO-hosted (chosen) | Client-hosted (rejected) |
|---|---|---|
| Cloudflare account owner | BlackCEO | Client |
| DNS / hostname brand | zerohumanworkforce.com (BlackCEO brand) | Client's own domain |
| Revocation | Instant, unilateral, API-scripted | Depends on client account access; reversible by client |
| Credentials needed | BlackCEO's own token only | Per-client Cloudflare tokens (doctrine violation) |
| PII residence | PII lives ON THE CLIENT'S OWN BOX (origin). Cloudflare only proxies and gates; BlackCEO's edge sees traffic in transit, stores nothing. | Same origin story, but transit rides client's edge |
| Client lock-in optics | Client uses a BlackCEO-branded URL | Client-branded URL |
| Ops burden | One account, one script set | N accounts, N script sets |

PII note for the record: the dashboard shows submitter first name, last name, email, phone,
and pipeline status. That data is stored in the episode records on the client's own box and
served by a loopback service on that box. Nothing client-identifying is stored in BlackCEO's
Cloudflare account except the hostname, the tunnel route, and the Access allow-list emails.
Per-client isolation holds: there is no shared origin, no shared database, no shared token.

Known exception to keep in mind: one TRACK B client runs their own operator-managed
Cloudflare account. Even that client is primarily routed via the standard rescue tunnel
pattern. The podcast engine uses the standard BlackCEO-hosted pattern for that client too
unless Trevor explicitly directs otherwise. Do not generalize this exception.

---

## 2. Tunnel topology

### 2.1 The shape (per client)

Each managed client box already runs ONE dedicated, named Cloudflare Tunnel (cloudflared,
absolute path /opt/homebrew/bin/cloudflared on Mac boxes). The podcast engine adds ingress
rules to that EXISTING tunnel. Do not create a second tunnel per client for this skill;
one tunnel per client, multiple hostnames, is the fleet pattern.

    Public edge (BlackCEO Cloudflare, zone zerohumanworkforce.com)
    |
    |-- <slug>.zerohumanworkforce.com            (existing Command Center, untouched)
    |       CNAME -> <tunnel-id>.cfargotunnel.com, proxied
    |       Cloudflare Access app (allow-by-email)
    |       tunnel ingress -> http://localhost:4000
    |
    |-- <slug>-podcast.zerohumanworkforce.com    (NEW: podcast dashboard)
    |       CNAME -> <tunnel-id>.cfargotunnel.com, proxied
    |       Cloudflare Access app "Podcast Dashboard - <slug>" (allow-by-email)
    |       tunnel ingress -> http://localhost:4010
    |
    |-- <slug>-hooks.zerohumanworkforce.com      (NEW or REUSED: inbound webhooks)
            CNAME -> <tunnel-id>.cfargotunnel.com, proxied
            NO Access app (machine-to-machine; see 2.3 auth layers)
            tunnel ingress -> http://127.0.0.1:18789
    |
    Origin (client's own box)
    |-- OpenClaw gateway        127.0.0.1:18789  (loopback only, receives /hooks/*)
    |-- Podcast dashboard svc   127.0.0.1:4010   (loopback only, read-only)
    |-- Command Center          127.0.0.1:4000   (existing, PM2/launchd)

Port assignment: the podcast dashboard service binds 127.0.0.1:4010 fleet-wide (4000 is the
Command Center; 4010 is reserved for this skill; the provisioner must check the port is free
and record the chosen port in the box's build-state file). The dashboard service is a small
read-only web server over the engine's episode records (the spec's data source requirement:
same records the engine produces, no separate data entry).

REUSE rule for the hooks hostname: several clients already receive GoHighLevel webhooks into
OpenClaw hooks. The provisioner must FIRST discover whether the box already has a public
hooks hostname routed to 127.0.0.1:18789 (query the Cloudflare API for the tunnel's ingress
config; never guess). If one exists, reuse it and only add the new hook mapping + secret.
If not, create `<slug>-hooks.zerohumanworkforce.com` as above. One hooks hostname per client
serves ALL inbound skills; per-skill separation happens at the hook path + token layer.

### 2.2 Zone and account constants (provisioner must hardcode or look up by name)

- Account ID: 13f808b72eb78027a8046357c6cf1afa (CLOUDFLARE_ACCOUNT_ID, correct).
- Zone zerohumanworkforce.com: a9ecc0a067f52eaa4c59dc9b11d9dd55.
- TRAP (earned in production): the CLOUDFLARE_ZONE_ID environment variable on the operator
  box points at businessaftersixty.com, NOT zerohumanworkforce.com. Using it silently
  creates malformed records that never resolve. Either hardcode the zone ID above or resolve
  it live via GET /zones?name=zerohumanworkforce.com. Never trust CLOUDFLARE_ZONE_ID.
- API token: CLOUDFLARE_API_TOKEN from the operator secret stores. Confirm SET, never print.

### 2.3 Inbound webhook: public URL + auth layers

The intake form submission (from Convert and Flow, Make.com, or n8n) POSTs to:

    https://<slug>-hooks.zerohumanworkforce.com/hooks/<podcast-intake-mapping>

which the tunnel delivers to the loopback OpenClaw gateway at 127.0.0.1:18789. Auth is
layered; all three layers are per-client:

1. OpenClaw hooks auth (primary). The hook mapping requires the per-client hooks token
   (Authorization bearer or token-in-path per current OpenClaw docs; LIVE-VERIFY the exact
   current mechanism at the openclaw.ai documentation, the brief mandates this research).
   The token is generated per client at provision time, stored in the client's environment
   stores (all three stores per fleet doctrine), and named for the skill, for example
   PODCAST_INTAKE_HOOK_TOKEN. Never shared across clients or skills.
2. Cloudflare WAF custom rule on the hooks hostname (edge filter): allow only method POST
   to path prefix /hooks/, block everything else (no GET probing of the gateway). Optionally
   add Cloudflare rate limiting on the hostname. LIVE-VERIFY what the current plan tier
   allows for custom rules + rate limiting on this zone.
3. cloudflared ingress path scoping where supported: the ingress rule for the hooks hostname
   can be scoped to path /hooks/* so nothing else on 18789 is reachable even if a WAF rule
   is misconfigured. LIVE-VERIFY current cloudflared ingress path-matching syntax.

Do NOT put Cloudflare Access in front of the hooks hostname by default. Access is built for
humans; webhook senders would need Access service tokens in custom headers. GoHighLevel's
Custom Webhook action can send custom headers, so Access service tokens are a viable
HARDENING OPTION (documented here for the future), but they add a second secret to rotate
and another failure mode at the exact ingress the whole engine depends on. Layer 1 + 2 is
the ship configuration; note the option in the runbook and move on.

Known OpenClaw hook mechanics that the build must respect (verified fleet knowledge):
- The gateway hook body from GoHighLevel must be FLAT (no nested objects) or every field
  resolves empty.
- deliver must be false for GoHighLevel-sourced hooks; the agent does its own outbound via
  the Convert and Flow API. This also keeps the engine silent (section 4).
- Hook sessions are single-turn; continuity, if ever needed, is file-based on the box.
- Config edits on Docker boxes run as the node user, never root (root-owned config freezes
  the gateway).

### 2.4 Dashboard: easiest possible client path

Design goal: the client should never manage a password, install anything, or think.

1. Provision (silent): the provisioner creates the hostname, Access app, and ingress; the
   Access app allow-list contains exactly: the client's own email address(es) from their
   onboarding record, trevelynotts@gmail.com, and trevor@blackceo.com. Nothing else. One
   app per client; never a wildcard app across clients.
2. Deliver the link ONCE, through the client's normal deliverable surfaces, both of which
   already exist and neither of which is operational spam:
   a. A "Podcast Studio" card/link on the client's existing Command Center
      (<slug>.zerohumanworkforce.com), added in harmony with the command center repo.
      The client already knows and uses that URL; the new card is discoverable in place.
   b. The dashboard URL is written to the client's Convert and Flow contact record custom
      field, and the standard onboarding workflow in Convert and Flow sends the one welcome
      message containing it. Convert and Flow owns customer messaging (responsibility
      boundary); OpenClaw never messages the client directly about this.
3. Open: the client clicks the link. Cloudflare Access prompts for their email and sends a
   one-time PIN (or Google single sign-on if they prefer). Correct email = in. No password,
   no account creation, no per-client secret to lose. Session persists per Access session
   policy, so day-to-day it is click-and-see.
   (Operator note: blackceo.com is on Cloudflare's one-time-PIN suppression list; Trevor
   signs in with Google single sign-on as trevor@blackceo.com, or with trevelynotts@gmail.com
   for PIN. Client domains are unaffected.)
4. Defense in depth on the data: the dashboard service binds loopback only and additionally
   requires a per-client bearer token (PODCAST_DASHBOARD_TOKEN, generated at provision,
   stored in the box environment stores) between the dashboard's server-side page layer and
   its data layer. The token never appears in browser-side code. Its only job is to make
   token rotation a meaningful revocation step (section 3, step 6) and to keep the data
   layer dead even if some future misconfiguration exposed the port.

Success signal for a healthy deployed dashboard (same as the Command Center pattern):
`curl -I https://<slug>-podcast.zerohumanworkforce.com` returns HTTP 302 to
sweet-wave-ca28.cloudflareaccess.com. That exact signal is the provision gate's pass check
AND the revocation gate's fail check (after revocation it must NOT return that 302).

---

## 3. ACCESS-REVOCATION RUNBOOK (client leaves)

Scripted as `revoke-podcast-client.sh <slug>` in the skill's scripts directory; every step
is idempotent (safe to re-run), every step logs to the operator ledger, and the script never
sends anything client-facing. Order matters: kill live sessions before deleting routes so
there is no window where a logged-in session outlives its hostname.

Preconditions: CLOUDFLARE_API_TOKEN confirmed SET (never printed); account ID
13f808b72eb78027a8046357c6cf1afa; zone ID a9ecc0a067f52eaa4c59dc9b11d9dd55 (hardcoded or
resolved by name; never the CLOUDFLARE_ZONE_ID environment variable).

LIVE-VERIFY: every endpoint below against current Cloudflare API docs before scripting;
paths and payload shapes drift.

Step 1 - Revoke live dashboard sessions (instant lockout).
  Find the Access app for <slug>-podcast.zerohumanworkforce.com:
    GET /accounts/{account_id}/access/apps?per_page=100  (filter by domain)
  Revoke all active sessions/tokens for it:
    POST /accounts/{account_id}/access/apps/{app_id}/revoke_tokens
  Effect: anyone currently logged in is bounced immediately, before any DNS TTL games.

Step 2 - Delete the Access application.
    DELETE /accounts/{account_id}/access/apps/{app_id}
  Effect: no new logins possible, allow-list gone. (If a partial offboard is ever wanted,
  for example pausing instead of ending, edit the app policy to an empty allow-list instead
  of deleting; default runbook = delete.)

Step 3 - Cut the dashboard hostname at DNS.
    GET  /zones/{zone_id}/dns_records?name=<slug>-podcast.zerohumanworkforce.com
    DELETE /zones/{zone_id}/dns_records/{record_id}
  Effect: hostname stops resolving at the edge.

Step 4 - Remove tunnel ingress routes (dashboard + podcast hook path).
  Determine how the client's tunnel is configured (LIVE-VERIFY per box):
  a. Remotely-managed tunnel (config lives in Cloudflare):
       GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations
       PUT the config back with the <slug>-podcast ingress rule removed.
       If the hooks hostname is used ONLY by the podcast engine, remove it too; if it is
       shared with other skills (GoHighLevel conversational hooks), leave the hostname and
       remove only the podcast hook mapping in Step 5.
  b. Locally-managed tunnel (config.yml on the box): edit the file over SSH, then restart
       cloudflared. Mac caveat (fleet doctrine): launchd LaunchAgents cannot be kickstarted
       over plain SSH (error 125); use the fleet-approved detached-restart pattern and never
       `brew services restart` a client Mac gateway path blindly. Restarting cloudflared is
       lower-risk than the gateway but follow the same discipline: prove the tunnel back
       healthy (edge connections > 0) before calling the step done.

Step 5 - Disable and rotate the inbound webhook.
  On the client box (as the correct runtime user, never root):
  a. Remove the podcast intake mapping from the OpenClaw hooks configuration (openclaw.json
     hooks.mappings, or whatever the current OpenClaw docs specify; LIVE-VERIFY).
  b. Rotate/delete PODCAST_INTAKE_HOOK_TOKEN in all environment stores on the box, so even
     a resurrected route is dead.
  c. Apply config per fleet gateway-restart doctrine (NEVER `openclaw gateway restart` over
     SSH on a Mac; use the MASTER-only kickstart or detached-run pattern; verify the gateway
     is back UP afterward; a revocation that downs a box that still runs other services is
     a failed revocation).
  d. If BlackCEO manages the client's Convert and Flow workflows, disable the intake form's
     webhook action there too. If the client owns it, our side is now deaf regardless.

Step 6 - Invalidate the dashboard token and stop the dashboard service.
  a. Rotate/delete PODCAST_DASHBOARD_TOKEN from the box environment stores.
  b. Stop and deregister the dashboard service (PM2 delete on VPS boxes; launchd/cron
     watchdog removal on Mac boxes, same SSH discipline as above).

Step 7 - Stop the daily credit smoke test for this client.
  The smoke test runs as an OpenClaw cron job on the client's box (see section 5). Remove it:
    openclaw cron list  ->  identify the podcast smoke-test job id  ->  openclaw cron rm <id>
  Also remove any plain crontab entry if the box uses the crontab fallback. Verify with a
  fresh `openclaw cron list` / `crontab -l` read that it is gone. This stops the daily paid
  API probes and stops founder alerts for a client who no longer exists.

Step 8 - Drain the credit-out queue for this client.
  Any podcast jobs held in the credit-out queue for this client are closed out as
  "client offboarded" (not "aged out"), and the founder is notified in the operator channel
  with the list of dropped job ids. Zero client-facing messages.

Step 9 - Independent end-to-end verification (no false done).
  a. `curl -sI https://<slug>-podcast.zerohumanworkforce.com` must NOT return 302 to
     sweet-wave-ca28.cloudflareaccess.com; expected: resolution failure or Cloudflare
     1016/530 class error.
  b. POST a dummy payload to the old hook URL: expected failure (route gone or hook 404;
     anything but a 2xx).
  c. Cloudflare API reads confirm: no Access app for the hostname, no DNS record, no
     ingress rule.
  d. Box reads confirm: no hook mapping, tokens absent from stores (check SET-ness only),
     dashboard service not running, cron gone, gateway still healthy.
  e. Write the per-item ledger entry (/tmp/<sweep>/<slug>.json pattern) and post the
     operator report. Only then is the revocation "done".

Ordering note: Steps 1-4 are pure Cloudflare API and require no box access; they alone fully
cut public access even if the box is unreachable. Steps 5-8 are box hygiene. The script must
therefore be able to run in "edge-only emergency mode" (steps 1-4 + 9a-c) when a box is dark,
and record the box-side steps as pending.

---

## 4. Silence: client-facing quiet, operator-verbose

1. Provisioning, health, revocation: zero messages to the client. No Telegram to the
   client's bot, no Convert and Flow messages, no email. The ONLY client-visible artifacts
   are the dashboard link delivered once through the standard Convert and Flow onboarding
   message and the Command Center card. MOVE IN SILENCE is doctrine.
2. Daily credit smoke test alerts go to the FOUNDER's operator channel only (the spec names
   Trevor Otts via the operator alerting channel, for example the operator/Rescue Rangers
   Telegram). The smoke test must never message the client, even on failure. The spec's
   credit-out alerts ("credits ran out, job queued, service named") are founder-directed too.
3. Cron hygiene: when creating the smoke-test cron via the OpenClaw command line, pass the
   no-deliver flag; the default delivery mode is announce and it will spam the client chat
   (known fleet drift bug). Verify delivery mode on the created job, not just the flag.
4. Never run standalone quality-check scripts on client boxes during maintenance if they
   emit client Telegram alerts (known leak in qc-completeness.sh standalone mode). The
   revocation and provision scripts must not source or trigger any client-notifying gate.
5. Operator-verbose means: every provision and every revocation writes a ledger entry and
   posts a full step-by-step report to the operator, including what was created/destroyed,
   the API call results, and the independent verification outputs. Sub-agents doing this
   work report every action unprompted.
6. deliver:false on all hook mappings (section 2.3) is part of silence: the gateway never
   auto-announces inbound webhook activity into any chat channel.

---

## 5. Provisioning summary (mirror of the revocation, for completeness)

`provision-podcast-client.sh <slug> <client-email(s)> <timezone>`:
1. Discover the client's existing tunnel id + config mode via the Cloudflare API.
2. Add ingress rules (dashboard :4010; hooks :18789 if not already present).
3. Create DNS CNAME(s) -> <tunnel-id>.cfargotunnel.com, proxied, in zone
   a9ecc0a067f52eaa4c59dc9b11d9dd55.
4. Create the Access app for the dashboard hostname, allow-list = client email(s) +
   trevelynotts@gmail.com + trevor@blackceo.com.
5. On-box: generate PODCAST_INTAKE_HOOK_TOKEN + PODCAST_DASHBOARD_TOKEN into the environment
   stores (confirm SET); add the OpenClaw hook mapping (flat body, deliver:false, per current
   OpenClaw docs); deploy the dashboard service on 127.0.0.1:4010 with a watchdog appropriate
   to the box type; apply gateway config per restart doctrine.
6. Create the daily credit smoke-test cron at ~06:00 in the CLIENT'S timezone, no-deliver,
   founder-alerting only, dirt cheap probes (balance endpoints where available; do not
   tighten the cadence; daily is the spec and tighter cadences are a token/credit furnace).
7. Write the dashboard URL to the Convert and Flow custom field; let the standard workflow
   deliver it. Add the Command Center card.
8. Gate: curl 302-to-Access check on the dashboard; signed test POST accepted on the hook;
   smoke-test cron fires once successfully; ledger + operator report. No pass, no done.

---

## 6. What the /goal build agent MUST research live (do not trust this doc's endpoint shapes)

At developers.cloudflare.com / the Cloudflare API reference:
1. Current Access application endpoints: create app, list apps, delete app, revoke_tokens,
   and Access policy schema (allow-by-email), plus Access session duration defaults and how
   fast revoke_tokens propagates.
2. Current tunnel configuration endpoints for remotely-managed tunnels
   (cfd_tunnel/{id}/configurations GET/PUT) vs locally-managed config.yml, and how to detect
   which mode a given tunnel uses. Also current cloudflared ingress path-matching syntax.
3. DNS record create/delete endpoints (v4 zones/{zone}/dns_records) current shape.
4. WAF custom rules + rate limiting: what the zone's current plan tier permits on
   zerohumanworkforce.com, and the current rulesets API for scoping method/path on one
   hostname.
5. Access service tokens (the documented hardening option for the hooks hostname) and
   whether GoHighLevel's Custom Webhook action reliably sends the CF-Access-Client-Id /
   CF-Access-Client-Secret headers.

At the openclaw.ai documentation (the brief separately mandates this):
6. The current inbound webhook (hooks) setup: endpoint format, token/auth mechanism, mapping
   schema (the strict key set), and payload expectations. The spec says the format is owned
   by OpenClaw and may change; follow the live docs, not fleet memory.

Per-box before touching anything:
7. Whether the box already has a hooks hostname routed to 127.0.0.1:18789 (reuse it),
   whether port 4010 is free, and the box type (Mac launchd vs VPS Docker/PM2) since restart
   and watchdog mechanics differ.

---

## 7. Risks and mitigations

- Tunnel config mode mismatch (remote vs local) -> provisioner detects, never assumes;
  both code paths implemented and tested on the operator's own box first (canary doctrine:
  prove on the operator box before any client box).
- Revocation while box unreachable -> edge-only emergency mode (section 3) fully cuts
  public access from the Cloudflare side alone.
- Shared hooks hostname collateral damage -> revocation removes only the podcast mapping
  and token when the hostname serves other skills; removes the hostname only when podcast
  is its sole tenant. The provisioner records tenancy in the ledger at provision time so
  revocation does not have to guess.
- Access app sprawl / wrong allow-list -> naming convention "Podcast Dashboard - <slug>";
  provision gate reads the policy back and diffs it against the intended email list.
- Zone ID trap -> hardcode or resolve by name; the script refuses to run if the resolved
  zone name is not zerohumanworkforce.com.
- Gateway downed during hook config apply on Mac boxes -> restart doctrine baked into the
  scripts; health probe after every apply; failed probe escalates to the operator channel,
  never "done".
