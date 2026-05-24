# n8n Workflow: command-center-register (v4)

This is the n8n webhook workflow at `https://main.blackceoautomations.com/webhook/command-center-register-v3` that Trevor's BlackCEO automation hub runs to provision new Command Center tunnels.

## The bug we found in v3 (fixed in v4 — 2026-05-24)

The v3 SSH command did `cloudflared tunnel create` + `route dns` + `tunnel token` but NEVER set tunnel **ingress** config. Token-based tunnels (`cloudflared tunnel run --token X`) use Cloudflare's remote-managed config — if ingress is empty, the tunnel returns HTTP 503 from CF edge even when the connector is healthy. Every client onboarded under v3 hit this: tunnel created, DNS resolved, connector connected, but the URL never served the dashboard.

This was confirmed by inspecting older tunnels in Trevor's CF account: the OLD working pattern was a single shared `command-center` tunnel where each new client was added as another hostname under that tunnel's ingress. When v3 switched to per-client tunnels, the ingress step got lost.

## The v4 fix

One curl call inserted between `route dns` and `tunnel token` in the SSH command, calling Cloudflare's PUT `/configurations` API to set ingress for the newly-created tunnel. Maps `<client>.zerohumanworkforce.com → http://localhost:4000` (where the Mission Control dashboard runs).

## Required env vars on main.blackceoautomations.com (the n8n SSH target)

The new curl call needs two env vars in the SSH user's shell environment:

- `CLOUDFLARE_ACCOUNT_ID` — Trevor's main CF account ID
- `CLOUDFLARE_API_TOKEN` — CF API token scoped to `Account > Cloudflare Tunnel: Edit`

For non-interactive SSH (which n8n uses), these typically need to live in `~/.profile` or `~/.ssh/environment` (with `PermitUserEnvironment yes` in `/etc/ssh/sshd_config`). Bash `~/.bashrc` is often NOT sourced on non-interactive sessions.

## The complete v4 SSH command

```bash
CLIENT="{{ $('Webhook: Client Registration').item.json.body.clientName }}"
cloudflared tunnel create $CLIENT > /dev/null 2>&1
TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "$CLIENT" | awk '{print $1}' | head -1)
cloudflared tunnel route dns -f $TUNNEL_ID ${CLIENT}.zerohumanworkforce.com > /dev/null 2>&1

# v4 — set tunnel ingress so CF edge routes to dashboard on :4000
curl -sS -X PUT "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"config\":{\"ingress\":[{\"hostname\":\"${CLIENT}.zerohumanworkforce.com\",\"service\":\"http://localhost:4000\"},{\"service\":\"http_status:404\"}]}}" > /dev/null

TOKEN=$(cloudflared tunnel token $TUNNEL_ID 2>/dev/null)
echo "TUNNEL_ID=$TUNNEL_ID"
echo "TUNNEL_TOKEN=$TOKEN"
echo "SUBDOMAIN=${CLIENT}.zerohumanworkforce.com"
```

## Backfill for tunnels created under v3 (one-time, on main.blackceoautomations.com)

```bash
ACCT="$CLOUDFLARE_ACCOUNT_ID"
TOKEN="$CLOUDFLARE_API_TOKEN"
curl -sS "https://api.cloudflare.com/client/v4/accounts/$ACCT/cfd_tunnel?per_page=50" \
  -H "Authorization: Bearer $TOKEN" | \
  python3 -c '
import json, sys, urllib.request, os
acct=os.environ["CLOUDFLARE_ACCOUNT_ID"]; tok=os.environ["CLOUDFLARE_API_TOKEN"]
for t in json.load(sys.stdin).get("result",[]):
    if t.get("deleted_at"): continue
    tid, name = t["id"], t["name"]
    cfg = json.load(urllib.request.urlopen(urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/cfd_tunnel/{tid}/configurations",
        headers={"Authorization": f"Bearer {tok}"})))
    ing = ((cfg.get("result") or {}).get("config") or {}).get("ingress") or []
    if [r for r in ing if r.get("hostname")]:
        print(f"  SKIP {name}: ingress already set")
        continue
    body = json.dumps({"config":{"ingress":[
        {"hostname": f"{name}.zerohumanworkforce.com", "service": "http://localhost:4000"},
        {"service": "http_status:404"}
    ]}}).encode()
    json.load(urllib.request.urlopen(urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/cfd_tunnel/{tid}/configurations",
        data=body, method="PUT",
        headers={"Authorization": f"Bearer {tok}", "Content-Type":"application/json"})))
    print(f"  PATCHED {name}")'
```

Applied this against Trevor's account on 2026-05-24 — patched 2 broken v3-era tunnels (lyric, evelyn). Both went 503 → 200 after their cloudflared connectors picked up the new remote config.
