# SOP-N8N-TUNNEL-01: SELF-HOSTED WEBHOOK INGRESS (n8n and equivalents)

**Cluster:** Universal SOPs (`universal-sops/`)
**Applies to:** any client agent operating a self-hosted service on the client's own box that must
receive INBOUND webhooks over the public internet — n8n is the flagship case, but the same pattern
covers any self-hosted automation, relay, or listener a department stands up on a client box.
**Owning department:** Fleet Infrastructure (operator-owned — Cloudflare zone, tunnels, and Access
policies belong to the operator, never the client)
**Consuming departments:** any department whose agent needs a public webhook endpoint for a
self-hosted service (Communications, Automations, integration builds under Skill 44, etc.)
**Cross-cutting references:** `38-conversational-ai-system/references/cloudflare-tunnel-troubleshooting.md`
(gateway/GHL tunnel failure-mode map — read this SOP first if the symptom is webhooks silently
failing on a self-hosted service, not the OpenClaw gateway itself), `shared-utils/cc-tunnel-ingress.sh`
(ingress-array merge helper — prevents a full-replace PUT from deleting a sibling hostname rule on a
shared tunnel), `32-command-center-setup/scripts/create-tunnel.sh` (the proven PM2-based
connector-install pattern Section 4 mirrors), `32-command-center-setup/INSTALL.md` Phase 6b/6c (the
same pattern narrated step-by-step, plus the PM2-persistence notes for Mac vs. Docker VPS),
`AGENTS.md`'s "Rescue Rangers — how to escalate" section (the ONLY real box→operator channel — this
SOP's Section 3.3 sends its escalation there), `platform/mac/service-selfheal/gateway-health-watchdog.sh`
(the fleet's own box-type detection logic — Section 3.1 mirrors it to tell a client agent whether it is
running inside a container with no docker CLI/socket).

---

## 0. WHAT THIS SOP IS

A client agent that needs to expose a self-hosted service's webhook endpoint to the public internet
(most commonly: a self-hosted n8n instance receiving inbound automation triggers) does **not**
provision its own Cloudflare tunnel the way a first-party OpenClaw gateway tunnel is provisioned. The
fleet's Cloudflare zone is **operator-owned**, and every box that has completed Command Center setup
already has exactly ONE tunnel and ONE connector running on it. This SOP is the one correct path from
"the client's service needs a public webhook URL" to "the webhook URL works and the rest of the
service stays locked down" — and the one hard guardrail that keeps an agent from wandering into a dead
end that can never succeed.

## 1. THE HARD GUARDRAIL — READ THIS FIRST

> ⛔ **Do NOT run `cloudflared tunnel login` (or any interactive `cloudflared`/Cloudflare-dashboard
> authentication) on a client box.** That command opens a browser and requires logging into a
> **Cloudflare account the person running it owns**. The client does not have a Cloudflare account on
> the fleet's zone — the operator does. The command will sit waiting for a login that can never
> complete, or it will succeed against the wrong (personal, empty) account and produce a tunnel that
> is not wired to anything. Every path through "have the client authenticate to Cloudflare" is a dead
> end. There is no version of this instruction that works for a client agent.

If you find yourself about to run `cloudflared tunnel login`, `cloudflared login`, or open
`dash.cloudflare.com` and ask the client (or yourself) to sign in — STOP. Go to Section 3 instead.

This is the same rule Skill 32's Command Center install already enforces at its own tunnel step
(`32-command-center-setup/INSTALL.md` Phase 6b gate check: *"Do NOT create a Cloudflare account. Do
NOT go to the Cloudflare website."*). This SOP exists because that same trap can reappear anywhere a
department stands up a NEW self-hosted service that needs its own public webhook path, not just the
Command Center dashboard.

## 2. THE ARCHITECTURE (why this is the correct shape)

```
Internet  →  Cloudflare DNS  →  THIS BOX'S EXISTING cloudflared connector  →  self-hosted service
                                          │
                                 Cloudflare Access
                          (protects the UI; bypassed for webhook paths only)
```

- The fleet runs **ONE cloudflared tunnel per box, carrying multiple hostnames on a single ingress
  array** — see `shared-utils/cc-tunnel-ingress.sh` lines 8-16 for the canonical shape (the Command
  Center dashboard, the OpenClaw gateway, the podcast board, and now this service, all as sibling
  rules on the SAME tunnel). A self-hosted service that needs a new public hostname does **not** get
  its own tunnel, its own token, or a second connector process — it gets **one new ingress rule**
  added to the box's existing tunnel. No new tunnel, no new token, no new connector, for the normal
  case (Section 4.1).
- The connector authenticates with a **tunnel TOKEN**, never an interactive login — that's how it got
  onto the box in the first place, via Command Center setup
  (`32-command-center-setup/scripts/create-tunnel.sh`, running under PM2 as `cloudflare-tunnel` on
  Mac AND on a Docker VPS). Adding a hostname to a tunnel that's already running is a change to that
  tunnel's ingress config, not a new authentication event, so nothing about THIS SOP requires issuing
  a new token. (Section 4.2 covers the rare exception — a box with no tunnel at all.)
- The ingress-rule addition is an entirely **operator-side, server-side** action against the
  Cloudflare API: `GET` the tunnel's current config → merge in the new hostname → `PUT` it back —
  never a full-replace `PUT`, which would silently delete the CC dashboard / gateway / podcast rules
  already sharing that array. The client agent's only job on the box itself is to confirm the
  connector is still up (Section 4.1) — there is nothing to install.
- **Why this can't go through Skill 38's client-owned Cloudflare token instead.** A box that has
  completed Skill 38 has its own client-owned `CLOUDFLARE_API_TOKEN` (see
  `38-conversational-ai-system/references/fleet-onboarding-tunnel-provisioning-field-guide.md`, Part
  4), and that token's permission set (`Cloudflare Tunnel: Edit`, `Access: Apps and Policies: Edit`,
  `DNS: Edit`) is broad enough that an agent could technically self-serve this hostname without asking
  anyone. **Do not do this.** That token lives on the CLIENT's own Cloudflare account and zone, and it
  provisions the OpenClaw gateway's own GHL-inbound tunnel there — a different tunnel, on a different
  account, for a different purpose. This SOP's hostname has to land on the box's EXISTING
  **operator-owned** tunnel (on `zerohumanworkforce.com` or another fleet zone) because that is the
  only tunnel the fleet's shared-ingress tooling (`shared-utils/cc-tunnel-ingress.sh`), QC scripts,
  and Access policies know how to reason about. Provisioning a second, client-zone tunnel for this
  service would technically work in isolation but would be invisible to all of that — exactly the
  divergent, un-modeled tunnel Section 0 exists to prevent. If both this SOP and Skill 38 are live on
  the same box, they are two DIFFERENT tunnels on two DIFFERENT Cloudflare accounts for two DIFFERENT
  purposes. Never merge them, and never reach for the Skill 38 token to solve this SOP's problem.
- **Cloudflare Access**, if applied to the whole hostname, puts every request behind a login wall —
  including inbound webhook callers (Telegram, GHL, Stripe, the self-hosted service's own automation
  partners) that cannot authenticate interactively. An Access policy scoped to the whole hostname
  SILENTLY breaks every webhook: the caller gets a 302 to a login page instead of a response, and
  nothing in the service's own logs shows an error because the request never reached the service.
- The fix is **NOT** "remove Access." It is a **path-scoped Access "Bypass (Everyone)" application**
  that covers only the webhook path(s) — e.g. `/webhook`, `/webhook-test`, `/webhook-waiting` for
  n8n — while the ROOT application (the UI, `/rest/*`, any admin path) stays behind Access exactly as
  before. Two applications on one hostname, split by path, not one all-or-nothing policy.

## 3. ESCALATE TO THE OPERATOR (the only client-agent action in this SOP)

The client agent's job here is to ask for the right things, correctly, once — not to attempt any of
the provisioning itself, and **never** to claim a check it did not actually run.

### 3.1 — Determine your box type FIRST (context detection)

Before anything else in this section — before any origin proof, before writing an escalation payload,
and certainly before typing any `docker` command — know which context you are actually in. This
mirrors the fleet's own box-type detection
(`platform/mac/service-selfheal/gateway-health-watchdog.sh`, box-type block, lines 67-91):

```bash
if [ -d /data/.openclaw ] && ! command -v docker >/dev/null 2>&1; then
  echo "vps-container"   # you ARE inside the OpenClaw container
elif [ -d "$HOME/.openclaw" ]; then
  echo "mac"
else
  echo "unknown — say so explicitly when you escalate, do not guess"
fi
```

In practice, `/data/.openclaw` existing is already the fleet's primary "inside the container" signal
(`gateway-health-watchdog.sh` lines 74-83) — a normal OpenClaw container on this fleet does not ship a
`docker` CLI at all, so the two conditions coincide. **`vps-container` is the normal case for a client
agent running on a Hostinger Docker VPS.** Confirmed fleet-wide by `gateway-health-watchdog.sh:66-70`
("inside the OpenClaw container … there is NO docker socket here"), the same file's heal-action block
at lines 196-202 ("Inside the container there is NO docker socket"), and
`platform/mac/service-selfheal/README.md:47-48` ("inside a container → log ESCALATE … no docker
socket"). No compose file in this repo mounts `/var/run/docker.sock` into the OpenClaw container, so
`docker compose ...` is **not** a fallback for a `vps-container` agent — it is a dead end
(`docker: command not found`).

If you are ever told (by this SOP or anything else) to run `docker compose exec` or
`docker compose ...` yourself: check this test first. If you are `vps-container`, skip straight to the
in-container instructions below (3.2) and in Section 5(a) — never fabricate having run a docker
command you could not run.

### 3.2 — Prove the candidate local origin responds (mandatory, box-type-aware)

Before asking the operator to wire an ingress rule, prove the port you're about to hand them actually
has something listening on THIS box — it saves a round trip if the port is wrong, and it's the
evidence the escalation payload's `alreadyTried` field needs.

**If you are `vps-container` or `mac` (the normal client-agent case — you share the service's network
namespace directly, no docker involved):** run `curl` **directly**:
```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:<candidate-port>   # e.g. :5678 for n8n
```
Any HTTP response code (even a `401`/`404`) proves the service is up and reachable from here — that is
all this check needs to show. A connection error (`curl: (7) Failed to connect`) means the service
isn't listening on that port yet; fix that before escalating, or say so plainly in the escalation's
`alreadyTried` field instead of skipping the step silently.

**If you are the OPERATOR running this from the VPS HOST session (NOT the client agent's own
context — a session with a working `docker` CLI that can see the compose project):** the
host-side-only equivalent is
```bash
docker compose exec <service> curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:<candidate-port>
```
This variant is for the operator/host-side session only — a client agent inside the container
(`vps-container`, 3.1) must never attempt it; there is no docker CLI or docker socket in that context.

### 3.3 — Send the escalation (Payload A) via the Rescue Rangers webhook

Escalate the same way every other unresolved problem on this fleet escalates — POST to
`$RESCUE_RANGERS_WEBHOOK_URL` per `AGENTS.md`'s "Rescue Rangers — how to escalate" section. This is
the **only** channel proven to cross the box→operator boundary (`AGENTS.md:562`). Do **not** use
`universal-sops/cross-dept-request-template.md` — every field in that template routes to
`{COMMAND_CENTER_URL}/api/tasks/...`, THIS box's own local Command Center, and never reaches the
operator. Do **not** send a direct Telegram message either — bot-to-bot Telegram never reaches the
rescue agent (`AGENTS.md:562`).

Fold the five provisioning asks into the `problem` field, and build `alreadyTried` from what you
**actually did** in 3.1/3.2 — never assert a check you did not run:

1. **A public hostname** for the service (e.g. `<client-slug>-n8n.zerohumanworkforce.com`).
2. **The service's local origin port** — the port confirmed listening in 3.2 (n8n defaults to `5678`).
3. **An ingress rule merged into this box's EXISTING tunnel**: `<hostname>` → `http://localhost:<PORT>`,
   added via `GET` → merge → `PUT` per `shared-utils/cc-tunnel-ingress.sh` — never a full-replace
   `PUT`, which would silently delete the CC dashboard / gateway / podcast rules already sharing that
   tunnel. State plainly that this is **not** a request for a new tunnel or a new token.
4. **Path-scoped Access "Bypass (Everyone)" applications** for the service's webhook paths only
   (state the exact paths — for n8n: `/webhook`, `/webhook-test`, `/webhook-waiting`; for another
   self-hosted service, the equivalent inbound-callback path(s)).
5. Confirmation that the **root application** (UI / `/rest/*` / admin) stays behind Access.

```bash
_RR_SECRET_ARGS=()
[ -n "${RESCUE_RANGERS_WEBHOOK_SECRET:-}" ] && _RR_SECRET_ARGS=(-H "X-Rescue-Secret: ${RESCUE_RANGERS_WEBHOOK_SECRET}")
curl -s -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  "${_RR_SECRET_ARGS[@]}" \
  -d '{
    "action":         "escalate",
    "person":         "<owner/end-user name>",
    "clientName":     "<client label>",
    "agentName":      "<your persona name>",
    "boxName":        "<hostname or compose-project label>",
    "boxType":        "<VPS | Mac Mini | MacBook Pro>",
    "openclawVersion":"<openclaw --version>",
    "problem":        "Need a public webhook hostname for a self-hosted service. Asks: (1) hostname,
                        e.g. <client-slug>-n8n.zerohumanworkforce.com; (2) local origin port <PORT>
                        (confirmed listening — see alreadyTried); (3) an ingress rule merged into this
                        box'\''s EXISTING tunnel via GET->merge->PUT, NOT a new tunnel/token/connector;
                        (4) path-scoped Access Bypass (Everyone) for <webhook paths>; (5) confirmation
                        the root app stays behind Access.",
    "alreadyTried":   "1. Box-type check (SOP-N8N-TUNNEL-01 Section 3.1): I am <vps-container | mac>.
                        2. Origin proof (Section 3.2): <EITHER: ran curl directly against
                        http://localhost:<PORT> (same network namespace, no docker needed) -> got HTTP
                        <code> OR, if it could not be run: origin proof could not be run: <reason> —
                        never claim a proof you did not perform.>",
    "returnTo":       "<client chat id>"
  }'
```

Do not proceed past this step until the operator has confirmed all five asks are provisioned — there
is nothing else for the agent to build in the meantime.

**What NOT to do while waiting:** do not attempt a workaround tunnel, do not install a second
`cloudflared` connector or start a second PM2-managed `cloudflared` process (the box's existing
connector already trusts the tunnel the operator is adding this hostname to), do not ask the client to
create their own Cloudflare account (the client is not the account owner and creating a second,
unrelated account solves nothing — the service still needs to sit on the OPERATOR's zone to get a
`zerohumanworkforce.com` subdomain and be reachable the way the rest of the fleet expects), do not
reach for the client's own Skill 38 `CLOUDFLARE_API_TOKEN` (Section 2), do not run any interactive
`cloudflared` auth command per Section 1, and do not run any `docker compose` command from inside the
container per Section 3.1.

## 4. ONCE PROVISIONED: CONFIRM THE CONNECTOR — DO NOT INSTALL A NEW ONE

### 4.1 — The normal case: this box already has a tunnel and a connector

Any box that has completed Command Center setup (Skill 32) already runs a `cloudflared` connector
under **PM2**, process name `cloudflare-tunnel` (installed by
`32-command-center-setup/scripts/create-tunnel.sh`, persisted across restarts by `pm2 startup` on Mac
and `pm2 resurrect` on a Docker VPS — see `32-command-center-setup/INSTALL.md` Phase 6c). The
operator's ingress-rule merge (Section 3.3, ask #3) attaches the new hostname to THIS existing tunnel —
it is a server-side change against the Cloudflare API, not something installed on the box. There is
nothing for the client agent to install, no new token to receive, no service to reinstall, and no
`systemctl`/`launchctl service install` step anywhere in this case — the fleet does not run
`cloudflared` under systemd or as a `launchd` service; it runs under PM2 on Mac and VPS alike.

The client agent's only job here is to confirm the connector is up — the identical command on Mac and
on a Docker VPS:

```bash
pm2 status cloudflare-tunnel   # expect status "online"
```

Once the operator confirms the ingress merge is live, move to Section 5 / Section 6 — no restart of
the connector is needed for a new hostname on an already-running tunnel.

### 4.2 — Greenfield case ONLY: this specific box has never had a tunnel at all

This should not happen on a box that has completed Command Center setup. **Verify first:**

```bash
pm2 list | grep cloudflare-tunnel
```

If that process exists at all — even stopped or errored — this is **not** the greenfield case; use
the "connector not running" row in Section 7 instead. Only if the process is entirely absent does the
box genuinely have no tunnel to merge into. In that case, say so explicitly in the Section 3.3
escalation; the operator will issue a full tunnel TOKEN instead of an ingress-merge-only response.

Store the token exactly the way Command Center's own install does. Environment variable name:
`CLOUDFLARE_TUNNEL_TOKEN`. Canonical location: `~/.openclaw/secrets/.env`, `chmod 600`. **Never echo,
print, or paste the token value onto a shell command line** — it lands in shell history the moment you
do (mirrors `32-command-center-setup/scripts/create-tunnel.sh` lines 66-79):

```bash
mkdir -p ~/.openclaw/secrets
# Write CLOUDFLARE_TUNNEL_TOKEN=<operator-provided token> into ~/.openclaw/secrets/.env by editing
# the file directly (or templating it in) — do not echo/print the token value to the terminal.
chmod 600 ~/.openclaw/secrets/.env
```

Start the connector under PM2 — the fleet's pattern on every box, Mac and VPS alike:

```bash
TUNNEL_TOKEN="$(grep '^CLOUDFLARE_TUNNEL_TOKEN=' ~/.openclaw/secrets/.env | cut -d= -f2-)"
pm2 delete cloudflare-tunnel 2>/dev/null || true
pm2 start "cloudflared tunnel run --token $TUNNEL_TOKEN" --name cloudflare-tunnel
pm2 save
pm2 status cloudflare-tunnel   # confirm "online"
```

If this prompts for a Cloudflare login at any point, the token was wrong or missing — go back to the
operator, do not fall back to `tunnel login`.

## 5. SET THE PUBLIC WEBHOOK URL ON THE SERVICE

Point the self-hosted service at the hostname the operator provisioned. For n8n, this is the
`WEBHOOK_URL` environment variable (n8n uses it to build the webhook URLs it shows in its own UI and
to validate inbound callback paths):

```bash
WEBHOOK_URL=https://<provisioned-hostname>/
```

Where this env var actually lives, and how to restart, depends on how the service was installed on
this box. Setting it in a shell and expecting it to persist is not enough — it has to land in the
service's own persistent environment.

**Mac, running as a background service (launchd):**
- The variable lives in that service's `.plist` (commonly `~/Library/LaunchAgents/<label>.plist` for
  a per-user agent, or `/Library/LaunchDaemons/<label>.plist` if it was installed to run at boot for
  all users), inside the `<key>EnvironmentVariables</key>` dict.
- Add or edit the `WEBHOOK_URL` key there, then restart so the change is picked up:
  ```bash
  launchctl kickstart -k gui/$(id -u)/<label>          # per-user LaunchAgent
  # or, if kickstart isn't available for this plist:
  launchctl unload ~/Library/LaunchAgents/<label>.plist
  launchctl load ~/Library/LaunchAgents/<label>.plist
  ```

**VPS — first determine which of the two shapes below actually applies.** Section 3.1's box-type check
tells you whether YOU are inside the OpenClaw container; it does not by itself tell you whether the
SELF-HOSTED SERVICE is a process PM2 manages inside that same container, or a separate docker-compose
service on the host. Check with:
```bash
pm2 list | grep -i <service-name>
```

**(a) The service runs under PM2, inside this same container (`pm2 list` shows it) — you CAN do this
yourself:**
- The variable lives in whatever persistent env source that PM2 process loads at start — its own
  `.env`/dotenv file, the `env:` block of a `pm2 ecosystem.config.js`, or a value exported in the shell
  before `pm2 start`. Inspect the process's resolved env first:
  ```bash
  pm2 describe <service-name>
  ```
  Edit the source it actually loads (not just the current shell — a bare `export` will not survive a
  `pm2 restart` unless you also pass `--update-env`), then apply:
  ```bash
  pm2 restart <service-name> --update-env
  ```
  `http://localhost:<PORT>` genuinely is the correct local origin here — you share this container's
  network namespace with the service (this is the ONE case where `localhost` on a VPS is correct; it
  is not a blanket exception, only this specific in-container-PM2 shape).

**(b) The service is a docker-compose service running on the VPS HOST, outside this container — you
CANNOT do this yourself:**
- The variable lives in the compose project's env file (`/docker/<project>/.env`) or the service's
  `environment:` block in `docker-compose.yml`, and applying it requires `docker compose up -d
  <service>` (never `docker compose restart`, which does NOT re-read `env_file` / `.env` changes) —
  all of it on the VPS HOST, which this container cannot reach: no docker CLI, no docker socket
  (Section 3.1).
- **This is an operator ask, not an agent action.** Do not attempt to edit
  `/docker/<project>/.env` or run any `docker compose` command from inside the container. Escalate via
  Section 3.3's Rescue Rangers channel using **Payload B** below instead.

**Payload B — VPS host-compose env-var ask (use only for shape (b) above):**
```bash
_RR_SECRET_ARGS=()
[ -n "${RESCUE_RANGERS_WEBHOOK_SECRET:-}" ] && _RR_SECRET_ARGS=(-H "X-Rescue-Secret: ${RESCUE_RANGERS_WEBHOOK_SECRET}")
curl -s -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  "${_RR_SECRET_ARGS[@]}" \
  -d '{
    "action":         "escalate",
    "person":         "<owner/end-user name>",
    "clientName":     "<client label>",
    "agentName":      "<your persona name>",
    "boxName":        "<hostname or compose-project label>",
    "boxType":        "VPS",
    "openclawVersion":"<openclaw --version>",
    "problem":        "The <service> hostname/ingress rule from Section 3 is already provisioned, but
                        <service> runs as a docker-compose service on the VPS HOST, not inside my
                        (OpenClaw) container. Need WEBHOOK_URL=https://<provisioned-hostname>/ set in
                        /docker/<project>/.env (or the compose environment: block for <service>), then
                        applied with `docker compose up -d <service>` — NOT `docker compose restart`,
                        which will not pick up the new value.",
    "alreadyTried":   "1. Box-type check (Section 3.1): vps-container — no docker CLI/socket here.
                        2. Confirmed <service> is NOT a PM2 process in this container (pm2 list does
                        not show it), so it must be the host'\''s compose service. I cannot edit
                        /docker/<project>/.env or run docker compose from this context.",
    "returnTo":       "<client chat id>"
  }'
```

A service that still shows `localhost` in its own webhook URLs after this step has not picked up the
new value — go back to whichever of (a)/(b) applies to this box and re-check that exact location and
restart command (or re-check with the operator, for case (b)) before moving on.

## 6. VERIFY — BOTH CHECKS ARE REQUIRED

A single "the site loads" check is not sufficient — it can pass while every webhook is still silently
eaten by Access. Run both:

**Check A — a webhook path reaches the app itself (expect a 404 FROM THE APP, not from Access):**
```bash
curl -sS -D - -o /tmp/n8n-tunnel-probe.html -w "HTTP_CODE:%{http_code}\n" -X POST \
  "https://<provisioned-hostname>/webhook/<any-probe-path>"
```
Expected: `HTTP_CODE:404`. A 404 here means the request reached the self-hosted service and the
service itself said "no route registered for that path" — which is correct for a probe path. If
instead you get a `302` — check the `Location:` header printed above; a missing bypass shows it
pointing at a `*.cloudflareaccess.com` login URL — or the body saved at `/tmp/n8n-tunnel-probe.html`
contains "Cloudflare Access" / login-page markup, the bypass application is missing or scoped wrong —
go back to the operator, do not try to fix Access policy yourself from the client box.

**Check B — the UI path is still protected (expect a 302 to Access):**
```bash
curl -sS -o /dev/null -w "%{http_code}\n" "https://<provisioned-hostname>/rest/login"
```
Expected: `302` (redirecting to the Access login page). **ANY other code means Access is NOT gating
the UI** — including `200` (n8n's own login page rendered directly), `401` (stock n8n's actual
unauthenticated response on `/rest/login` when nothing is in front of it — this is the realistic
failure code, not `200`; do not wave off a `401` here as "close enough"), or `404`. Any of these means
the request reached n8n directly instead of being stopped at Access: the bypass was applied too
broadly and the admin surface is exposed with no authentication. This is a defect; report it to the
operator immediately, do not leave it as-is.

**Both conditions must hold at the same time.** Webhook path unauthenticated + UI path still gated is
the only passing state. Either one alone is a defect.

## 7. ESCALATION PATHS

| Situation | Action |
|---|---|
| Need a public webhook URL for a self-hosted service | Section 3.3 — escalate to operator via the Rescue Rangers webhook with the five asks (Payload A). Never attempt `cloudflared tunnel login`, never provision a second tunnel or connector yourself. |
| I am inside the OpenClaw container (no docker CLI/socket, Section 3.1) and the service or its env-var config lives on the VPS HOST, outside this container | Escalate via Section 3.3 with **Payload B** (Section 5(b)) — state the exact origin/env change needed. Do NOT improvise, do NOT attempt any `docker compose` command from here, do NOT start a second connector. |
| Origin proof (Section 3.2) cannot be run in my context — no `curl`, service not started yet, or box type indeterminate | Say so plainly in the escalation's `alreadyTried` field (Section 3.3) — never assert a proof you could not run. Escalate with whatever box-type context you DID determine (Section 3.1) and let the operator confirm the rest. |
| `pm2 status cloudflare-tunnel` / `pm2 list \| grep cloudflare-tunnel` shows nothing — the connector process does not exist at all | This box never completed Command Center's own tunnel setup — outside this SOP's normal scope (Section 4.1 assumes that tunnel already exists). Escalate to the operator and confirm before assuming Section 4.2 (greenfield) applies; do not hand-start a connector outside PM2 (e.g. `cloudflared service install` / a raw `cloudflared tunnel run` outside PM2) — that produces a second, unmanaged process the fleet's tooling and restart-persistence (`pm2 startup`/`pm2 resurrect`) don't track. |
| Greenfield connector (Section 4.2) prompts for a Cloudflare login | Token is wrong/missing. Stop, report to operator, do not fall back to interactive auth. |
| Check A returns 302 / an Access login page instead of 404 | Bypass application missing or misconfigured. Escalate to operator — do not edit Access policy from the client box. |
| Check B returns anything other than 302 (200, 401, 404, ...) | Bypass scoped too broadly — the UI is unauthenticated. Escalate to operator immediately; this is an exposed-admin-surface defect, not a webhook problem. |
| Service still shows `localhost` in its own webhook URLs after setting the public hostname | `WEBHOOK_URL` (or equivalent) not picked up — see Section 5 for the exact env-var location and restart command for this box's install type (launchd plist, in-container PM2, or VPS host-compose); re-check and restart (or re-escalate, for the host-compose case) before re-testing. |
| A shared tunnel's ingress rule for this host disappears after another service's install script runs | Full-replace ingress PUT clobbered it. See `shared-utils/cc-tunnel-ingress.sh` — any tunnel-ingress writer must GET → merge → PUT, never a bare full-replace. |

## 8. WHY THIS SOP EXISTS

An agent that hits a wall provisioning Cloudflare for a client — no token, no clear next step written
down anywhere — has generic training knowledge of the `cloudflared` CLI, including `cloudflared tunnel
login`, and generic training knowledge of `cloudflared service install` / systemd unit files that has
nothing to do with how this fleet actually runs its connectors. Without an explicit guardrail and an
explicit escalation path, the natural move under pressure is to try the command that "should" work. It
will never work for a client box, it burns time chasing a browser flow that can't complete or a second
connector process the fleet's tooling doesn't know about, and it can confuse the client if the agent
narrates the dead end to them instead of escalating quietly. Section 1's guardrail plus Section 3's
escalation path close that gap: there is always a next step, and the next step is never "log in to an
account you don't have" or "install a connector the fleet doesn't use."
