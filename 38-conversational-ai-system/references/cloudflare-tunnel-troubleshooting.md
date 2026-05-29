# Cloudflare Tunnel — Troubleshooting (Phase 1-2)

> Deep-dive reference for the v5.14 playbook Phase 1 (Build Network Plumbing) +
> Phase 2 (Configure OpenClaw). See `references/v6.0-source-playbook.md` Steps 1, 2,
> 3, 3.5, 4 for the canonical setup steps. This file is the failure-mode map.

## The 4 layers between GHL and OpenClaw

Inbound message path:
```
GHL  →  Cloudflare DNS  →  cloudflared tunnel  →  OpenClaw gateway (localhost:18789)  →  agent
```

When inbound messages don't reach the agent, one of those four layers broke. The order
to check is the order they're listed.

## Layer 1 — Cloudflare DNS

Symptom: GHL webhook delivery fails with DNS error or 5xx from `<tunnel-hostname>.<zone>`.

Check:
- `dig +short <tunnel-hostname>.<zone>` should return a proxied CNAME to `<tunnel-id>.cfargotunnel.com`.
- The CNAME must be PROXIED (orange cloud), not DNS-only.
- The zone must be active in the Cloudflare account that owns the tunnel.

Fix:
- Re-create the CNAME via the Cloudflare API. The v5.14 playbook Step 1 has the exact
  curl invocation.

## Layer 2 — cloudflared tunnel

Symptom: DNS resolves, but TLS connection times out or returns 502.

Check:
- `systemctl status cloudflared` (Linux) or `launchctl list | grep cloudflared` (Mac).
- The tunnel's ingress config must list the tunnel hostname → `http://localhost:18789`.
- The tunnel's connector token must match the one created via API.

Fix:
- Reinstall as a persistent system service (Step 2 of the v5.14 playbook). On Mac use
  `sudo cloudflared service install <TOKEN>`; on Linux use the apt-package post-install
  systemd unit. Skill 38's `04-register-crons.sh` does NOT manage cloudflared — that
  lives in Phase 1 of the playbook itself.

## Layer 3 — OpenClaw gateway

Symptom: tunnel is up and serving, but the gateway returns no response or 500.

Check:
- `openclaw gateway status` should report `Listening: 127.0.0.1:18789`.
- `openclaw config validate` must pass.
- `hooks.mappings` must contain a `ghl-inbound` entry (and `stripe-events`,
  `shopify-events` if those integrations are active).

Fix:
- `openclaw gateway restart` — Trevor's Mac is master-agent-restartable (see his
  memory rules). Client gateways need owner approval.

## Layer 4 — agent

Symptom: gateway accepts the inbound webhook but the agent never produces a reply.

Check:
- AGENTS.md Step 1.7-1.9 + Step 2.8 are present (see `scripts/05-update-agents-md.sh`).
- The 8 channel playbooks exist under `<MASTER_FILES_DIR>/communication-playbooks/`.
- The conversation log directory exists and is writable.

Fix:
- Re-run skill 38's `00-verify-prerequisites.sh` then `05-update-agents-md.sh`.
- If the agent is stuck on a cron, check `openclaw cron list` for stuck `weekly-tune-up`
  or `proactive-suggestions-scan` jobs.

## The Cloudflare OTP suppression on blackceo.com (operator-specific)

Per Trevor's memory: CF Access PIN emails to blackceo.com are silently blocked
(suppression list separate from general CF notifications). When wiring CF Access for
this skill's Command Center handoff, use `trevelynotts@gmail.com` for fleet
operator-access, NOT blackceo.com addresses.

