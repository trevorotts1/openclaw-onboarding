TASK: Enable OpenClaw to accept the inbound Cloudflare Tunnel that's already wired
up for this Mac. The tunnel is configured to route https://openclaw.<clientdomain>
to http://localhost:18789. cloudflared is (or is about to be) running on this Mac.
You need to make OpenClaw's gateway accept browser/HTTP requests that arrive
through the tunnel.

CONTEXT (do not skip):
- Per docs.openclaw.ai/gateway/configuration-reference, the gateway listens on
  127.0.0.1:18789 by default and serves the Control UI, the Admin HTTP RPC, the
  inbound webhook endpoint, and the WebSocket gateway — all on that one port.
- The cloudflared connector dials localhost:18789 from inside this Mac, so the
  gateway SHOULD stay loopback-bound. Do NOT change gateway.bind. Keep it loopback.
- Per docs.openclaw.ai/gateway/security, Cloudflare Tunnel does NOT provide
  identity headers (only Tailscale Serve does). Therefore do NOT switch
  gateway.auth.mode to "trusted-proxy". Keep the default shared-secret auth.
- The ONLY thing OpenClaw blocks by default is browser Origin: when a request
  arrives with Origin: https://openclaw.<clientdomain>, the gateway
  rejects it unless that origin is in gateway.controlUi.allowedOrigins.
- hooks.enabled=true REQUIRES a non-empty hooks.token that is DISTINCT from
  gateway.auth.token. The webhook receiver validates the token via either
  Authorization: Bearer <token> or x-openclaw-token: <token> headers.
  Query-string tokens are rejected.

STEP 1 — Pre-flight: confirm gateway state
Run: openclaw gateway status
Expect "Capability: write-capable" and "Connectivity probe: ok". If not, run
`openclaw doctor --fix` before proceeding.

STEP 2 — Add the tunnel hostname to allowedOrigins (merge if non-empty)
  CURRENT=$(openclaw config get gateway.controlUi.allowedOrigins --json 2>/dev/null || echo '[]')
  MERGED=$(echo "$CURRENT" | jq -c '. + ["https://openclaw.<clientdomain>"] | unique')
  openclaw config set gateway.controlUi.allowedOrigins "$MERGED"

STEP 3 — Confirm Control UI basePath (informational only, do NOT change)
Run: openclaw config get gateway.controlUi.basePath
Default is "/openclaw". The full external URL will be:
  https://openclaw.<clientdomain><basePath>/
Note this for the verification step.

STEP 4 — Enable the inbound webhook endpoint CORRECTLY
Hooks require BOTH a token AND enabled=true. Set them in this exact order so the
gateway never sees a partial state:

  # 4a. Generate a strong random token (64 hex chars, distinct from gateway.auth.token)
  HOOKS_TOKEN=$(openssl rand -hex 32)
  echo "$HOOKS_TOKEN" > /tmp/openclaw-hooks-token  # tmp file for retrieval

  # 4b. Sanity check: must NOT equal the gateway auth token
  GW_TOKEN=$(openclaw config get gateway.auth.token --json 2>/dev/null | tr -d '"')
  if [ "$HOOKS_TOKEN" = "$GW_TOKEN" ]; then
    echo "FATAL: hooks token collided with gateway token; regenerating"
    HOOKS_TOKEN=$(openssl rand -hex 32)
  fi

  # 4c. Set token FIRST, then path, then flip enabled to true
  openclaw config set hooks.token "$HOOKS_TOKEN"
  openclaw config set hooks.path "/hooks"
  openclaw config set hooks.enabled true

  # 4d. Persist token to a 600-mode credentials file so the operator can
  # send webhooks later
  mkdir -p ~/.openclaw/credentials  # VPS: /data/.openclaw/credentials
  echo "$HOOKS_TOKEN" > ~/.openclaw/credentials/hooks.token
  chmod 600 ~/.openclaw/credentials/hooks.token

STEP 5 — Reload the gateway so config takes effect
Run: openclaw gateway reload  (fall back to `openclaw gateway restart`)
Wait 5 seconds, then re-run `openclaw gateway status` and confirm it's
write-capable again.

STEP 6 — Verify locally that the gateway + webhook endpoint are listening
  curl -sI http://127.0.0.1:18789/openclaw/ | head -3
  # any 2xx/3xx/401 is fine — proves Control UI is up

  curl -sI -H "Authorization: Bearer $HOOKS_TOKEN" \
       http://127.0.0.1:18789/hooks | head -3
  # 2xx/4xx is fine; a connection-refused or 5xx means hooks didn't load

  # CRITICAL: confirm no fresh gateway.startup_failed in last 60 seconds
  ls -t ~/.openclaw/logs/stability/*gateway.startup_failed*.json 2>/dev/null | head -1 \
    | xargs -I{} sh -c 'AGE=$(( $(date +%s) - $(stat -f %m {}) )); echo "latest crash log age: ${AGE}s"'
  # AGE > 60s = healthy. AGE < 60s = something's still broken; re-read the JSON for the error.

STEP 7 — Confirm cloudflared is running and connected
  sudo launchctl list | grep cloudflare
  # at least one entry with a non-zero PID
  # if not installed yet, install with the tunnel token from Trevor:
  #   brew install cloudflared
  #   sudo cloudflared service install <TUNNEL_TOKEN>
  #   sudo launchctl start com.cloudflare.cloudflared

STEP 7b — Harden the connector (Wi-Fi QUIC idle-timeout fix)
cloudflared defaults to QUIC (UDP). Consumer Wi-Fi routers age out idle UDP NAT
mappings in minutes, causing repeated 6s drops (CF error 1033). Fix: switch the
connector to http2 (TCP) and install a 20s keepalive agent.

  # Layer A+B+D: force TCP, unconditional KeepAlive, AC no-sleep (requires sudo, once).
  sudo bash platform/mac/tunnel-hardening/harden-mac-tunnel.sh

  # Layer C: 20s edge ping -- keeps NAT mapping warm (no sudo).
  bash platform/mac/tunnel-hardening/install-keepalive-agent.sh

  # Layer D-nosudo: */5 connector watchdog (no sudo).
  bash platform/mac/tunnel-hardening/install-watchdog-agent.sh

After running, confirm:
  /usr/libexec/PlistBuddy -c "Print :ProgramArguments" \
    /Library/LaunchDaemons/com.cloudflare.cloudflared.plist | grep http2
  # Expected: http2 is present

  launchctl print gui/$(id -u)/com.clawd.tunnel-keepalive | grep 'pid ='
  # Expected: a non-zero PID

  tail -5 /tmp/clawd-tunnel-keepalive.log
  # Expected (after ~20s): [<ts>] edge-ping ok

See platform/mac/tunnel-hardening/README.md for full details and the verify block.

STEP 8 — Report back to Trevor with these exact fields:
  - openclaw gateway status output (verbatim)
  - openclaw config get gateway.controlUi.allowedOrigins (verbatim, post-merge)
  - openclaw config get gateway.controlUi.basePath (verbatim)
  - openclaw config get hooks.enabled (verbatim)
  - openclaw config get hooks.path (verbatim)
  - hooks.token (first 12 chars only — Trevor will retrieve the full one from
    ~/.openclaw/credentials/hooks.token via SSH)
  - sudo launchctl list | grep cloudflare output (verbatim)
  - curl -sI http://127.0.0.1:18789/openclaw/ first line
  - The full external URL: https://openclaw.<clientdomain><basePath>/
  - The stability-log age for last gateway.startup_failed (must be > 60s — proves no crash loop)

DO NOT:
  - Set hooks.enabled=true WITHOUT also setting hooks.token in the same operation.
    The gateway will refuse to start with: "Error: hooks.enabled requires hooks.token"
  - Reuse gateway.auth.token as hooks.token. The gateway rejects it explicitly:
    "hooks.token must be distinct from gateway.auth.token"
  - Pass tokens via query string. The webhook receiver rejects them; only the
    Authorization: Bearer or x-openclaw-token headers are accepted.
  - Change gateway.bind (must stay "loopback" — cloudflared is the only public path)
  - Change gateway.auth.mode to "trusted-proxy" (Cloudflare does not provide
    identity headers; that mode is for Tailscale Serve only)
  - Set gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback to true
    (security downgrade; allowedOrigins is the correct fix)
  - Forward X-Forwarded-* headers from any local reverse proxy
