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
shared tunnel), `32-command-center-setup/INSTALL.md` Phase 6b (the proven operator-token pattern this
SOP generalizes).

---

## 0. WHAT THIS SOP IS

A client agent that needs to expose a self-hosted service's webhook endpoint to the public internet
(most commonly: a self-hosted n8n instance receiving inbound automation triggers) does **not**
provision its own Cloudflare tunnel the way a first-party OpenClaw gateway tunnel is provisioned. The
fleet's Cloudflare zone is **operator-owned**. This SOP is the one correct path from "the client's
service needs a public webhook URL" to "the webhook URL works and the rest of the service stays
locked down" — and the one hard guardrail that keeps an agent from wandering into a dead end that can
never succeed.

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
Internet  →  Cloudflare DNS  →  cloudflared connector (token-based, no login)  →  self-hosted service
                                          │
                                 Cloudflare Access
                          (protects the UI; bypassed for webhook paths only)
```

- The **connector** (`cloudflared`) on the client box authenticates with a **tunnel TOKEN**, not a
  login. A token is a bearer credential issued by the operator's Cloudflare account for one specific
  tunnel; installing it is `cloudflared service install <TOKEN>` (or `cloudflared tunnel run --token
  <TOKEN>`) — no browser, no account, no interactive step.
- The tunnel is created and lives **inside the operator's Cloudflare account**, the same account that
  owns `zerohumanworkforce.com` / the fleet's other zones. The client's box only ever holds the token,
  never the account credentials.
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
the provisioning itself. Send the operator a message with exactly these four asks:

1. **A public hostname** for the service (e.g. `<client-slug>-n8n.zerohumanworkforce.com`).
2. **A tunnel token** for that hostname, scoped to this box.
3. **Path-scoped Access "Bypass (Everyone)" applications** for the service's webhook paths only
   (state the exact paths — for n8n: `/webhook`, `/webhook-test`, `/webhook-waiting`; for another
   self-hosted service, the equivalent inbound-callback path(s)).
4. Confirmation that the **root application** (UI / `/rest/*` / admin) stays behind Access — i.e.
   confirm the bypass is scoped, not a removal of Access from the whole hostname.

Use the standard cross-department/operator request shape (`universal-sops/cross-dept-request-template.md`)
if the fleet's request-logging convention applies on this box; otherwise a direct, specific Telegram
message covering the four asks above is sufficient. Do not proceed past this step until the operator
has confirmed all four are provisioned — there is nothing else for the agent to build in the meantime.

**What NOT to do while waiting:** do not attempt a workaround tunnel, do not ask the client to create
their own Cloudflare account (the client is not the account owner and creating a second, unrelated
account solves nothing — the service still needs to sit on the OPERATOR's zone to get a
`zerohumanworkforce.com` subdomain and be reachable the way the rest of the fleet expects), and do not
run any interactive `cloudflared` auth command per Section 1.

## 4. ONCE PROVISIONED: INSTALL THE CONNECTOR (token-based, no login)

**Mac (root LaunchDaemon):**
```bash
sudo cloudflared service install "$TUNNEL_TOKEN"
sudo launchctl list | grep com.cloudflare.cloudflared   # confirm it registered
```

**VPS (systemd service, or the box's existing service manager):**
```bash
sudo cloudflared service install "$TUNNEL_TOKEN"
sudo systemctl is-enabled cloudflared   # must return "enabled"
sudo systemctl is-active cloudflared    # must return "active"
```

Neither command opens a browser or prompts for a Cloudflare login. If either one DOES prompt for
credentials, the token was wrong or missing — go back to the operator, do not fall back to
`tunnel login`.

## 5. SET THE PUBLIC WEBHOOK URL ON THE SERVICE

Point the self-hosted service at the hostname the operator provisioned. For n8n, this is the
`WEBHOOK_URL` environment variable (n8n uses it to build the webhook URLs it shows in its own UI and
to validate inbound callback paths):

```bash
WEBHOOK_URL=https://<provisioned-hostname>/
```

Restart the service after setting it. A service that still shows `localhost` in its own webhook URLs
after this step has not picked up the new value — re-check the env var location and restart path
before moving on.

## 6. VERIFY — BOTH CHECKS ARE REQUIRED

A single "the site loads" check is not sufficient — it can pass while every webhook is still silently
eaten by Access. Run both:

**Check A — a webhook path reaches the app itself (expect a 404 FROM THE APP, not from Access):**
```bash
curl -sS -o /dev/null -w "%{http_code}\n" -X POST "https://<provisioned-hostname>/webhook/<any-probe-path>"
```
Expected: `404`. A 404 here means the request reached the self-hosted service and the service itself
said "no route registered for that path" — which is correct for a probe path. If instead you get a
`302` (redirect to a Cloudflare Access login page) or the response body contains "Cloudflare Access" /
"Login" text, the bypass application is missing or scoped wrong — go back to the operator, do not try
to fix Access policy yourself from the client box.

**Check B — the UI path is still protected (expect a 302 to Access):**
```bash
curl -sS -o /dev/null -w "%{http_code}\n" "https://<provisioned-hostname>/rest/login"
```
Expected: `302` (redirecting to the Access login page). If this returns `200` or the service's own
login page instead, the bypass was applied too broadly — it is now covering the UI as well as the
webhook paths, which means the admin surface is exposed with no authentication. This is also a defect;
report it to the operator, do not leave it as-is.

**Both conditions must hold at the same time.** Webhook path unauthenticated + UI path still gated is
the only passing state. Either one alone is a defect.

## 7. ESCALATION PATHS

| Situation | Action |
|---|---|
| Need a public webhook URL for a self-hosted service | Section 3 — escalate to operator with the four asks. Never attempt `cloudflared tunnel login`. |
| Connector install prompts for a Cloudflare login | Token is wrong/missing. Stop, report to operator, do not fall back to interactive auth. |
| Check A returns 302 / an Access login page instead of 404 | Bypass application missing or misconfigured. Escalate to operator — do not edit Access policy from the client box. |
| Check B returns 200 (UI unauthenticated) | Bypass scoped too broadly. Escalate to operator immediately — this is an exposed-admin-surface defect, not a webhook problem. |
| Service still shows `localhost` in its own webhook URLs after setting the public hostname | `WEBHOOK_URL` (or equivalent) not picked up — re-check env var location and restart the service before re-testing. |
| A shared tunnel's ingress rule for this host disappears after another service's install script runs | Full-replace ingress PUT clobbered it. See `shared-utils/cc-tunnel-ingress.sh` — any tunnel-ingress writer must GET → merge → PUT, never a bare full-replace. |

## 8. WHY THIS SOP EXISTS

An agent that hits a wall provisioning Cloudflare for a client — no token, no clear next step written
down anywhere — has generic training knowledge of the `cloudflared` CLI, including `cloudflared tunnel
login`. Without an explicit guardrail and an explicit escalation path, the natural move under pressure
is to try the command that "should" work. It will never work for a client box, it burns time chasing a
browser flow that can't complete, and it can confuse the client if the agent narrates the dead end to
them instead of escalating quietly. Section 1's guardrail plus Section 3's escalation path close that
gap: there is always a next step, and the next step is never "log in to an account you don't have."
